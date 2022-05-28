#!/usr/bin/python3

import logging
import re
import shutil
import subprocess

from collections import ChainMap
from datetime import datetime
from functools import cached_property
from itertools import chain
from pathlib import Path

from ..base import SauceryBase
from ..reduction import Reductions
from ..reduction.analysis.analysis import Analysis

from .analyse import SOSAnalysis
from .analyse import SOSAnalysisError
from .extract import SOSExtraction
from .extract import SOSExtractionError
from .meta import SOSMetaDict
from .meta import SOSMetaProperty


LOGGER = logging.getLogger(__name__)


class SOS(SauceryBase):
    FILENAME_REGEX = re.compile(r'(?i)'
                                r'(?P<name>sosreport-(?P<hostname>.+?)(?:-(?P<case>\d+)-(?P<date>\d{4}-\d{2}-\d{2})-(?P<hash>\w{7}))?)' # noqa
                                r'\.(?P<ext>tar(?:\.(?P<compression>(xz|gz|bz2)))?)$')

    def __init__(self, *args, sosreport, **kwargs):
        super().__init__(*args, **kwargs)
        self._sosreport = sosreport

        # Require sanely named sosreport
        self._sosreport_match = self.FILENAME_REGEX.match(self.sosreport.name)
        if not self._sosreport_match:
            raise ValueError(f"Invalid sosreport name '{self.sosreport.name}'")

    def __repr__(self):
        return str(self.sosreport)

    @property
    def defaultconfig(self):
        return {'reductions': str(self.saucery.saucerydir / 'reductions')}

    @cached_property
    def sosreport(self):
        return Path(self._sosreport).resolve()

    def exists(self):
        return self.sosreport.is_file()

    @property
    def name(self):
        return self._sosreport_match.group('name')

    @property
    def ext(self):
        return self._sosreport_match.group('ext')

    @property
    def compression(self):
        return self._sosreport_match.group('compression')

    @property
    def reductionsdir(self):
        return self.config.get('reductions')

    @cached_property
    def reductions(self):
        return Reductions(self, self.reductionsdir)

    @cached_property
    def workdir(self):
        return self.sosreport.parent / self.name

    @property
    def linesdir(self):
        return self.workdir / 'lines'

    @property
    def filesdir(self):
        return self.workdir / 'files'

    def file(self, filename, *, command=None):
        d = self.filesdir
        if command:
            d = d / 'sos_commands' / command
        return d / filename

    def _file_read(self, filename, func, *, command=None, strip=False):
        try:
            f = self.file(filename, command=command)
            content = getattr(f, func)()
        except FileNotFoundError:
            return None
        if strip:
            content = content.strip()
        return content

    def file_text(self, filename, **kwargs):
        return self._file_read(filename, 'read_text', **kwargs)

    def file_bytes(self, filename, **kwargs):
        return self._file_read(filename, 'read_bytes', **kwargs)

    @property
    def isodate(self):
        cmd = ['date', '--iso-8601=seconds', '--utc']
        for filename in ['date_--utc', 'hwclock', 'date']:
            sosdate = self.file_text(filename, command='date', strip=True)
            if not sosdate:
                continue
            result = subprocess.run(cmd + [f'--date={sosdate}'],
                                    stdout=subprocess.PIPE, encoding='utf-8')
            if result.returncode == 0:
                return result.stdout.strip()
        return None

    @property
    def datetime(self):
        if self.isodate:
            return datetime.fromisoformat(self.isodate)
        return None

    @property
    def hostname(self):
        return self.file_text('hostname', strip=True)

    @property
    def machineid(self):
        return self.file_text('etc/machine-id', strip=True)

    @property
    def json(self):
        LOGGER.debug(f'Generating JSON for {self.name}')

        conclusions = {level: len(list(chain(*[c.get('results') for c in self.conclusions
                                               if c.get('abnormal') and c.get('level') == level])))
                       for level in Analysis.VALID_LEVELS}

        result = {
            'name': self.name,
            'sosreport': self.sosreport.name,
            'datetime': self.isodate,
            'hostname': self.hostname,
            'machineid': self.machineid,
            'case': self.case,
            'customer': self.customer,
        }
        if self.conclusions:
            result['conclusions'] = conclusions
        return result

    invalid = SOSMetaProperty('invalid', bool)
    extracted = SOSMetaProperty('extracted', bool)
    files_json = SOSMetaProperty('files.json', 'json')
    total_size = SOSMetaProperty('total_size', int)

    def extract(self, reextract=False):
        if self.invalid and not reextract:
            LOGGER.error(f'Invalid sosreport, not extracting: {self.name}')
            return

        if self.filesdir.exists():
            if reextract or not self.extracted:
                partial = '' if self.extracted else 'partial '
                LOGGER.info(f'Removing existing {partial}data at {self.filesdir}')
                if not self.dry_run:
                    shutil.rmtree(self.filesdir)
            else:
                LOGGER.info(f'Already extracted, not re-extracting: {self.filesdir}')
                return

        LOGGER.info(f'Extracting: {self.sosreport.name} -> {self.filesdir}')
        if self.dry_run:
            return

        self.extracted = False
        del self.invalid
        del self.files_json
        del self.total_size

        e = SOSExtraction(self)
        try:
            e.extract()
        except SOSExtractionError as e:
            LOGGER.error(f'Invalid sosreport, error extracting: {self.sosreport}: {e}')
            LOGGER.exception(e)
            self.invalid = True
            return

        self.files_json = e.members
        self.total_size = sum((m.get('size') for m in e.get_members('file')))
        self.extracted = True

    analysed = SOSMetaProperty('analysed', bool)
    conclusions = SOSMetaProperty('conclusions', 'json')

    def analyse(self, reanalyse=False):
        if not self.filesdir.exists() or not self.extracted:
            LOGGER.error(f"Not extracted, can't analyse: {self.name}")
            return

        if self.analysed:
            if reanalyse:
                LOGGER.info(f'Re-analysing {self.name}')
            else:
                LOGGER.info(f'Already analysed, not re-analysing {self.name}')
                return
        else:
            LOGGER.info(f'Analysing {self.name}')

        if self.dry_run:
            return

        self.analysed = False
        del self.conclusions

        self.lookup_case()
        self.lookup_customer()
        self.lookup_meta()

        a = SOSAnalysis(self)
        try:
            a.analyse()
        except SOSAnalysisError as e:
            LOGGER.error(f'Error analysing: {self.sosreport}: {e}')
            LOGGER.exception(e)
            return
        LOGGER.info(f'Finished analysing sosreport: {self.name}')

        self.conclusions = a.conclusions
        self.analysed = True

    case = SOSMetaProperty('case')

    def lookup_case(self):
        if self.case:
            LOGGER.debug(f"Already have 'case', skipping lookup: {self.name}")
            return
        self.case = self.lookup('case')
        if self.case:
            LOGGER.info(f"Set 'case' to '{self.case}' based on lookup: {self.name}")
            return
        self.case = self._sosreport_match.group('case')
        if self.case:
            LOGGER.info(f"Set 'case' to '{self.case}' based on filename: {self.name}")

    customer = SOSMetaProperty('customer')

    def lookup_customer(self):
        if self.customer:
            LOGGER.debug(f"Already have 'customer', skipping lookup: {self.name}")
            return
        self.customer = self.lookup('customer')
        if self.customer:
            LOGGER.info(f"Set 'customer' to '{self.customer}' based on lookup: {self.name}")

    @cached_property
    def meta(self):
        return SOSMetaDict(self, self.config.get('meta', '').split())

    def lookup_meta(self):
        lookedup = []
        for key in self.meta.keys():
            if self.meta.get(key):
                LOGGER.debug(f"Already have meta '{key}', skipping: {self.name}")
                continue
            self.meta[key] = self.lookup(f'meta_{key}')
            if self.meta.get(key):
                lookedup.append(key)
        if lookedup:
            LOGGER.info(f"Looked up meta values '{','.join(lookedup)}': {self.name}")

    def lookup(self, key):
        cmd = self.config.get(key)
        if not cmd:
            LOGGER.debug(f"No config for '{key}', skipping: {self.name}")
            return None
        cmd = [c.format_map(ChainMap({'meta': ''}, vars(self))) for c in cmd.split()]
        cmdstr = ' '.join(cmd)

        LOGGER.debug(f"Lookup for '{key}': {cmdstr}")
        try:
            result = subprocess.run(cmd, encoding='utf-8',
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.SubprocessException:
            LOGGER.exception(f"Error running '{cmdstr}': {self.name}")
            return None

        if result.returncode != 0:
            LOGGER.error(f"Error ({result.returncode}) running '{cmdstr}': {self.name}")
            if result.stderr.strip():
                LOGGER.error(result.stderr)
            return None

        LOGGER.debug(f"Looked up '{key}': {self.name}")
        return result.stdout
