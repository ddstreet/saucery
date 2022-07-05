#!/usr/bin/python3

import logging
import re
import shutil
import subprocess

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
from .mapping import SOSMapping
from .persistent import DirDict
from .persistent import FileProperty
from .squash import SOSSquash
from .squash import SOSSquashError


LOGGER = logging.getLogger(__name__)


class SOS(SauceryBase):
    @classmethod
    def match_filename(cls, filename):
        return SOSFilenamePattern.match(filename)

    @classmethod
    def valid_filename(cls, filename):
        return cls.match_filename(filename) is not None

    def __init__(self, *args, sosreport, **kwargs):
        super().__init__(*args, **kwargs)
        self._sosreport = sosreport

        # Require sanely named sosreport
        self._sosreport_match = self.match_filename(self.sosreport.name)
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
    def mapping(self):
        return SOSMapping(self)

    @cached_property
    def workdir(self):
        return self.sosreport.parent / self.name

    @property
    def filesdir(self):
        return self.workdir / 'files'

    @cached_property
    def analysis_files(self):
        return DirDict(self.workdir / 'analysis_files')

    def under_filesdir(self, path):
        try:
            Path(path).resolve().relative_to(self.filesdir.resolve())
            return True
        except ValueError:
            return False

    def commanddir(self, command):
        if '/' in str(command):
            LOGGER.error(f"Invalid command '{command}'")
            return None
        d = self.filesdir / 'sos_commands' / command
        if not self.under_filesdir(d):
            LOGGER.error(f"Invalid command '{command}'")
            return None
        return d

    def fileglob(self, fileglob, *, command=None):
        d = self.commanddir(command) if command else self.filesdir
        if not d:
            return None
        return [p for p in d.glob(str(fileglob).lstrip('/'))
                if self.under_filesdir(p)]

    def file(self, filename, *, command=None):
        d = self.commanddir(command) if command else self.filesdir
        if not d:
            return None
        path = d / str(filename).lstrip('/')
        if not self.under_filesdir(path):
            LOGGER.error(f"Invalid filename '{filename}'")
            return None
        return path

    def analysis_file(self, filename):
        return self.analysis_files.path(filename)

    def _file_read(self, filename, func, *, command=None, strip=False):
        try:
            f = self.file(filename, command=command)
            if not f:
                return None
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

    invalid = FileProperty('invalid', bool)
    extracted = FileProperty('extracted', bool)
    files_json = FileProperty('files.json', 'json')
    total_size = FileProperty('total_size', int)

    def extract(self, *args, **kwargs):
        self._extract(*args, **kwargs)
        return self.extracted

    def _extract(self, reextract=False):
        if self.invalid and not reextract:
            LOGGER.error(f'Invalid sosreport, not extracting: {self.name}')
            return

        if self.squashed and not reextract:
            LOGGER.info(f'Already squashed, not extracting (try mounting instead): {self.name}')
            return

        if self.filesdir.exists():
            if reextract or not (self.extracted or self.mounted):
                if self.mounted:
                    if not self.unmount():
                        return
                else:
                    partial = '' if self.extracted else 'partial '
                    LOGGER.info(f'Removing existing {partial}data at {self.filesdir}')
                    if not self.dry_run:
                        shutil.rmtree(self.filesdir)
            else:
                LOGGER.info(f'Already extracted, not re-extracting: {self.filesdir}')
                return

        LOGGER.info(f'Extracting {self.sosreport.name} to {self.filesdir}')

        if self.dry_run:
            return

        self.extracted = False
        del self.invalid
        del self.files_json
        del self.total_size

        extractor = SOSExtraction(self)
        try:
            extractor.extract()
        except SOSExtractionError as e:
            LOGGER.error(f'Invalid sosreport, error extracting: {self.sosreport}: {e}')
            LOGGER.exception(e)
            self.invalid = True
            return

        LOGGER.info(f'Extracted {self.sosreport.name} to {self.filesdir}')

        self.files_json = extractor.members
        self.total_size = sum((m.get('size') for m in extractor.get_members('file')))
        self.extracted = True

    @property
    def squashimg(self):
        return self.workdir / 'squash.img'

    squashed = FileProperty('squashed', bool)

    def squash(self, *args, **kwargs):
        self._squash(*args, **kwargs)
        return self.squashed

    def _squash(self, resquash=False):
        if self.squashed and not resquash:
            LOGGER.info(f'Already squashed, not re-squashing: {self.name}')
            return

        if not self.filesdir.exists() or not self.extracted:
            LOGGER.error(f"Not extracted, can't squash: {self.name}")
            return

        if self.squashimg.exists():
            LOGGER.info(f'Removing existing img at {self.squashimg}')
            if not self.dry_run:
                self.squashimg.unlink()

        LOGGER.info(f'Squashing {self.filesdir} to {self.squashimg}')

        if self.dry_run:
            return

        self.squashed = False

        squasher = SOSSquash(self)
        try:
            squasher.squash()
        except SOSSquashError as e:
            LOGGER.error(f'Error squashing: {self.sosreport}: {e}')
            LOGGER.exception(e)
            return

        LOGGER.info(f'Finished squashing {self.squashimg}')
        LOGGER.info(f'Removing {self.filesdir}')

        self.squashed = True
        self.extracted = False
        shutil.rmtree(self.filesdir)

    @property
    def mounted(self):
        return self.filesdir.is_mount()

    def mount(self, *args, **kwargs):
        self._mount(*args, **kwargs)
        return self.mounted

    def _mount(self, remount=False):
        if not self.squashimg.exists() or not self.squashed:
            LOGGER.error(f"Not squashed, can't mount: {self.name}")
            return

        if self.filesdir.exists():
            if remount or not (self.extracted or self.mounted):
                if self.mounted:
                    if not self.unmount():
                        return
                else:
                    partial = '' if self.extracted else 'partial '
                    LOGGER.info(f'Removing existing {partial}data at {self.filesdir}')
                    if not self.dry_run:
                        shutil.rmtree(self.filesdir)
            else:
                if self.extracted:
                    LOGGER.info(f'Not mounting over extracted files: {self.filesdir}')
                elif self.mounted:
                    LOGGER.info(f'Already mounted, not re-mounting: {self.filesdir}')
                return

        LOGGER.info(f'Mounting {self.squashimg} at {self.filesdir}')

        if self.dry_run:
            return

        squasher = SOSSquash(self)
        try:
            squasher.mount()
        except SOSSquashError as e:
            LOGGER.error(f'Error mounting {self.squashimg}: {e}')
            LOGGER.exception(e)

        LOGGER.info(f'Finished mounting {self.filesdir}')

    def unmount(self, *args, **kwargs):
        self._unmount(*args, **kwargs)
        return not self.mounted

    def umount(self):
        '''Alias for unmount(), to match unix "umount" cmd'''
        return self.unmount()

    def _unmount(self):
        if not self.mounted:
            LOGGER.info(f'Not mounted: {self.name}')
            return

        LOGGER.info(f'Unmounting {self.filesdir}')

        if self.dry_run:
            return

        squasher = SOSSquash(self)
        try:
            squasher.unmount()
        except SOSSquashError as e:
            LOGGER.error(f'Error unmounting {self.squashimg}: {e}')
            LOGGER.exception(e)
            return

        LOGGER.info(f'Finished umounting {self.filesdir}')

        self.filesdir.rmdir()

    analysed = FileProperty('analysed', bool)
    conclusions = FileProperty('conclusions', 'json')
    case = FileProperty('case')
    customer = FileProperty('customer')

    def analyse(self, *args, **kwargs):
        self._analyse(*args, **kwargs)
        return self.analysed

    def _analyse(self, reanalyse=False):
        if not self.filesdir.exists() or not (self.extracted or self.mounted):
            LOGGER.error(f"Not extracted/mounted, can't analyse: {self.name}")
            return

        if self.analysed:
            if reanalyse:
                LOGGER.info(f'Ignoring existing analysis for {self.name}')
            else:
                LOGGER.info(f'Already analysed, not re-analysing {self.name}')
                return

        LOGGER.info(f'Analysing {self.name}')

        if self.dry_run:
            return

        self.analysed = False
        del self.conclusions
        self.analysis_files.clear()
        # Note, we keep existing case/customer values here

        a = SOSAnalysis(self)
        try:
            a.analyse()
        except SOSAnalysisError as e:
            LOGGER.error(f'Error analysing: {self.sosreport}: {e}')
            LOGGER.exception(e)
            return

        LOGGER.info(f'Finished analysing sosreport: {self.name}')

        # Don't replace case/customer values if set, since that info may have
        # been manually set and/or not 'detectable' from only the sosreport
        if self.case:
            LOGGER.debug(f"Already have 'case', skipping lookup: {self.name}")
        else:
            self.case = a.case
        if self.customer:
            LOGGER.debug(f"Already have 'customer', skipping lookup: {self.name}")
        else:
            self.customer = a.customer

        self.conclusions = a.conclusions
        self.analysed = True


def _SOSFilenamePattern():
    # The parts are separated to attempt making it easier to understand the full regex pattern
    COMPRESSION = r'(?P<compression>(xz|gz|bz2))'
    EXT = fr'(?P<ext>tar(?:\.{COMPRESSION})?)'
    HASH = r'(?P<hash>\w{7})'
    DATE = r'(?P<date>\d{4}-\d{2}-\d{2})'
    CASE = r'(?P<case>\d+)'
    HOSTNAME = r'(?P<hostname>.+?)'
    NAME = fr'(?P<name>sosreport-{HOSTNAME}(?:-{CASE}-{DATE}-{HASH})?)'
    return re.compile(fr'(?i){NAME}\.{EXT}')


SOSFilenamePattern = _SOSFilenamePattern()
