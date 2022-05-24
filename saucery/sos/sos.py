#!/usr/bin/python3

import magic
import re
import shutil
import subprocess
import tarfile
import tempfile

from collections import defaultdict
from datetime import datetime
from functools import cached_property
from itertools import chain
from pathlib import Path

from saucery.base import SauceryBase
from saucery.reduction import Reductions
from saucery.reduction.analysis.analysis import Analysis
from .meta import SOSMetaDict
from .meta import SOSMetaProperty


class SOS(SauceryBase):
    def __init__(self, *args, sosreport, **kwargs):
        super().__init__(*args, **kwargs)
        self._sosreport = sosreport

        # Require sanely named sosreport
        self._sosreport_match = self.SOSREPORT_REGEX.match(self.sosreport.name)
        if not self._sosreport_match:
            raise ValueError(f"Invalid sosreport name '{self.sosreport.name}'")

    def __repr__(self):
        return str(self.sosreport)

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

    @cached_property
    def workdir(self):
        return self.sosreport.parent / self.name

    case = SOSMetaProperty('case')
    customer = SOSMetaProperty('customer')

    @cached_property
    def meta(self):
        return SOSMetaDict(self, self.config.get('meta', '').split())

    seared = SOSMetaProperty('seared', bool)
    conclusions = SOSMetaProperty('conclusions', 'json')

    def sear(self, resear=False):
        if not self.filesdir.exists() or not self.extracted:
            self.LOGGER.error(f"Not extracted, can't sear: {self.name}")
            return

        if not self.case:
            filename_case = self._sosreport_match.group('case')
            if filename_case:
                self.LOGGER.info(f'Setting case to {filename_case} based on filename: {self.name}')
                self.case = filename_case
            else:
                self.LOGGER.error(f"Case unset and not in filename, can't sear: {self.name}")
                return

        if self.seared:
            if resear:
                self.LOGGER.info(f'Re-searing {self.name}')
            else:
                self.LOGGER.info(f'Already seared, not re-searing {self.name}')
                return
        else:
            self.LOGGER.info(f'Searing {self.name}')

        if self.dry_run:
            return

        self.seared = False

        for key in self.meta.keys():
            if self.meta.get(key) and not resear:
                self.LOGGER.debug(f"Already have meta '{key}', skipping: {self.name}")
                continue
            cmd = self.config.get(f'meta_{key}')
            if not cmd:
                self.LOGGER.warning(f"No config for meta '{key}', skipping: {self.name}")
                continue
            self.LOGGER.debug(f"Getting meta '{key}': {cmd} {self.filesdir}")
            try:
                result = subprocess.run(cmd.split() + [self.filesdir], encoding='utf-8',
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.SubprocessException:
                self.LOGGER.exception(f"Error getting meta '{key}': {self.name}")
                continue
            if result.returncode != 0:
                self.LOGGER.error(f"Error ({result.returncode}) getting meta '{key}': {self.name}")
                if result.stderr.strip():
                    self.LOGGER.error(result.stderr)
                continue
            self.meta[key] = result.stdout
            self.LOGGER.info(f"Set meta '{key}': {self.name}")
        self.LOGGER.info(f'Finished setting meta values: {self.name}')

        conclusions = []
        for a in self.reductions.analyses:
            self.LOGGER.debug(f'Getting conclusion for {a.name}: {self.name}')
            try:
                conclusions.append(dict(a.conclusion))
            except Exception:
                self.LOGGER.exception(f'Analysis {a.name} failed, skipping')
        self.conclusions = conclusions
        self.LOGGER.info(f'Finished analysing sosreport: {self.name}')

        self.seared = True

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

    def _file_read(self, filename, func, *, command=None, strip=True):
        try:
            f = self.file(filename, command=command)
            content = getattr(f, func)()
        except FileNotFoundError:
            return None
        if strip:
            return content.strip()
        return content

    def file_text(self, filename, **kwargs):
        return self._file_read(filename, 'read_text', **kwargs)

    def file_bytes(self, filename, **kwargs):
        return self._file_read(filename, 'read_bytes', **kwargs)

    invalid = SOSMetaProperty('invalid', bool)
    extracted = SOSMetaProperty('extracted', bool)
    file_list = SOSMetaProperty('file_list')
    file_count = SOSMetaProperty('file_count', int)
    total_size = SOSMetaProperty('total_size', int)

    def extract(self, *, reextract=False):
        if self.invalid and not reextract:
            self.LOGGER.error(f'Invalid sosreport, not extracting: {self.name}')
            return

        if self.filesdir.exists():
            if reextract or not self.extracted:
                partial = '' if self.extracted else 'partial '
                self.LOGGER.info(f'Removing existing {partial}data at {self.filesdir}')
                if not self.dry_run:
                    shutil.rmtree(self.filesdir)
            else:
                self.LOGGER.info(f'Already extracted, not re-extracting: {self.filesdir}')
                return

        if self.linesdir.exists() and not self.dry_run:
            shutil.rmtree(self.linesdir)

        self.LOGGER.info(f'Extracting: {self.sosreport.name} -> {self.filesdir}')
        if self.dry_run:
            return

        if not self.workdir.exists():
            self.workdir.mkdir(parents=False, exist_ok=False)

        self.invalid = False
        self.extracted = False
        members = defaultdict(list)
        try:
            with tempfile.TemporaryDirectory(dir=self.workdir) as tmpdir:
                top = None
                dest = Path(tmpdir).resolve()
                with tarfile.open(self.sosreport) as tar:
                    for m in tar:
                        topdir = m.name.split('/')[0]
                        if not top:
                            top = topdir
                        elif top != topdir:
                            raise ValueError(f'Multiple top-level dirs: {top}, {topdir}')
                        self._extract_member(tar, dest, m, members)
                if not top:
                    raise ValueError('No files found in sosreport')
                # Rename the top-level 'sosreport-...' dir so our files/ dir contains the content
                dest.joinpath(top).rename(self.filesdir)
        except Exception as e:
            self.LOGGER.error(f'Invalid sosreport, error extracting: {self.sosreport}: {e}')
            self.LOGGER.exception(e)
            self.invalid = True
            return

        self.file_list = '\n'.join(members['file']) + '\n'
        self.file_count = len(members['file'])
        self.total_size = sum(members['size'])

        self.LOGGER.info(f'Extracted {self.file_count} members '
                         f'({self.total_size} bytes): {self.filesdir}')
        self.extracted = True

    def _extract_member(self, tar, dest, m, members):
        path = dest.joinpath(m.name).resolve()
        mname = '/'.join(m.name.split('/')[1:])
        if not str(path).startswith(str(dest)):
            self.LOGGER.warning(f"Skipping invalid member path '{m.name}': {self.name}")
            mtype = 'invalid'
        elif m.isdir():
            path.mkdir(mode=0o775)
            mtype = 'dir'
        elif getattr(m, 'linkname', None):
            if not str(path.parent.joinpath(m.linkname).resolve()).startswith(str(dest)):
                self.LOGGER.warning(f"Skipping invalid file '{m.name}' "
                                    f"link path '{m.linkname}': {self.name}")
            path.symlink_to(m.linkname)
            mtype = 'link'
            lines_path = self.linesdir / mname
            lines_path.parent.mkdir(parents=True, exist_ok=True)
            lines_path.symlink_to(m.linkname)
        elif m.ischr():
            self.LOGGER.debug(f"Ignoring char node '{m.name}': {self.name}")
            mtype = 'chr'
        elif m.isblk():
            self.LOGGER.debug(f"Ignoring block node '{m.name}': {self.name}")
            mtype = 'blk'
        elif m.isfifo():
            self.LOGGER.debug(f"Ignoring fifo node '{m.name}': {self.name}")
            mtype = 'fifo'
        elif m.isfile():
            tar.extract(m, path=dest)
            mode = path.stat().st_mode
            path.chmod(mode | 0o644)
            mtype = 'file'
            members['size'].append(m.size)
            filetype = magic.from_file(str(path), mime=True)
            members['filetype'] = set(members['filetype']) | set((filetype,))
            if filetype.startswith('text'):
                self._detect_newlines(path, mname)
        else:
            self.LOGGER.debug(f"Ignoring unknown type '{m.type}' member '{m.name}': {self.name}")
            mtype = 'unknown'
        members[mtype].append(mname)

    def _detect_newlines(self, path, name):
        lines = [newline.end() for newline in re.finditer(b'^|\n|(?<!\n)$', path.read_bytes())]
        lines_path = self.linesdir / name
        lines_path.parent.mkdir(parents=True, exist_ok=True)
        lines_path.write_text(','.join(map(str, lines)))

    @property
    def datetime(self):
        if self.isodate:
            return datetime.fromisoformat(self.isodate)
        return None

    @cached_property
    def isodate(self):
        cmd = ['date', '--iso-8601=seconds', '--utc']
        for filename in ['date_--utc', 'hwclock', 'date']:
            sosdate = self.file_text(filename, command='date')
            if not sosdate:
                continue
            result = subprocess.run(cmd + [f'--date={sosdate}'],
                                    stdout=subprocess.PIPE, encoding='utf-8')
            if result.returncode == 0:
                return result.stdout.strip()
        return None

    @property
    def hostname(self):
        return self.file_text('hostname')

    @property
    def machineid(self):
        return self.file_text('etc/machine-id')

    @property
    def reductionsdir(self):
        return self.kwargs.get('reductions', self.config.get('reductions'))

    @cached_property
    def reductions(self):
        return Reductions(self, self.reductionsdir)

    def _conclusions_level_count(self, level):
        level = level.lower()
        if level not in Analysis.VALID_LEVELS:
            raise ValueError(f'Invalid analysis level {level}: {self.name}')
        conclusions = self.conclusions
        if not conclusions:
            return '?'
        return len(list(chain(*[c.get('results') for c in conclusions
                                if c.get('abnormal') and c.get('level') == level])))

    @property
    def json(self):
        self.LOGGER.debug(f'Generating JSON for {self.name}')
        return {
            'name': self.name,
            'sosreport': self.sosreport.name,
            'datetime': self.isodate,
            'hostname': self.hostname,
            'machineid': self.machineid,
            'case': self.case,
            'customer': self.customer,
            'conclusions': {level: self._conclusions_level_count(level)
                            for level in Analysis.VALID_LEVELS},
        }
