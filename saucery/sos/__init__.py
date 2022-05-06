#!/usr/bin/python3

import shutil
import subprocess
import tarfile
import tempfile

from collections import ChainMap
from datetime import datetime
from functools import cached_property
from pathlib import Path
from types import MappingProxyType

from saucery.base import SauceryBase
from saucery.reduction import Reductions
from saucery.sos.meta import SOSMetaDict
from saucery.sos.meta import SOSMetaProperty


__all__ = ['SOS']


class SOS(SauceryBase):
    @classmethod
    def check(cls, filename):
        '''Check validity of tar file.

        Raises ValueError if provided filename is not tar file,
        or if any member of the tar file is absolute or contains
        "/../" path elements.
        '''
        cls.LOGGER.debug(f'Checking tar file {filename}')
        if not tarfile.is_tarfile(filename):
            raise ValueError(f'sosreport is not tar: {filename}')
        try:
            with tarfile.open(filename) as tar:
                for name in tar.getnames():
                    if name.startswith('/') or name.startswith('..') or '/../' in name:
                        raise ValueError(f'Invalid tar member: {name}')
        except EOFError:
            raise ValueError('Invalid/corrupt tarfile')

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

    @cached_property
    def meta(self):
        keys = self.configsection('sosreport_meta').get('lookup_keys', '').split()
        return SOSMetaDict(self, keys)

    seared = SOSMetaProperty('seared', bool)
    analysis = SOSMetaProperty('analysis', 'json')

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

        initial_keys = {
            'case': self.case,
            'sosreport_files': str(self.filesdir),
        }
        sosreport_meta = self.lookup('sosreport_meta', initial_keys)
        if not sosreport_meta:
            self.LOGGER.error(f'Failed to set sosreport meta: {self.name}')
            return

        for k, v in sosreport_meta.items():
            self.meta[k] = v
        self.LOGGER.info(f'Finished setting sosreport meta: {self.name}')

        conclusions = []
        for a in self.reductions.analyses:
            self.LOGGER.debug(f'Getting conclusion for {a.name}: {self.name}')
            conclusions.append(dict(a.conclusion))
        self.analysis = conclusions
        self.LOGGER.info(f'Finished analysing sosreport: {self.name}')

        self.seared = True

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

    extracted = SOSMetaProperty('extracted', bool)
    file_list = SOSMetaProperty('file_list')
    file_count = SOSMetaProperty('file_count', int)
    total_size = SOSMetaProperty('total_size', int)

    def extract(self, *, reextract=False):
        if self.filesdir.exists():
            if reextract or not self.extracted:
                partial = '' if self.extracted else 'partial '
                self.LOGGER.info(f'Removing existing {partial}data at {self.filesdir}')
                if not self.dry_run:
                    shutil.rmtree(self.filesdir)
            else:
                self.LOGGER.info(f'Already extracted, not re-extracting: {self.filesdir}')
                return

        self.LOGGER.info(f'Extracting: {self.sosreport.name} -> {self.filesdir}')
        if self.dry_run:
            return

        if not self.workdir.exists():
            self.workdir.mkdir(parents=False, exist_ok=False)

        self.extracted = False
        file_list = ''
        file_count = 0
        total_size = 0
        try:
            with tempfile.TemporaryDirectory(dir=self.workdir) as tmpdir:
                with tarfile.open(self.sosreport) as tar:
                    for m in tar:
                        if m.isdev():
                            continue
                        tar.extract(m, path=tmpdir)
                        file_list += f'{m.name}\n'
                        file_count += 1
                        if m.issym():
                            continue
                        total_size += m.size
                        mode = 0o775 if m.isdir() else 0o664
                        (Path(tmpdir) / m.name).chmod(mode)
                topfiles = list(Path(tmpdir).iterdir())
                if len(topfiles) == 0:
                    raise ValueError(f'No files found in sosreport: {self.name}')
                if len(topfiles) > 1:
                    raise ValueError(f'sosreport contains multiple top-level dirs: {tmpdir}')
                # Rename the top-level 'sosreport-...' dir so our files/ dir contains the content
                topfiles[0].rename(self.filesdir)
        except Exception as e:
            self.LOGGER.exception(e)
            raise
        finally:
            self.file_list = file_list
            self.file_count = file_count
            self.total_size = total_size
        self.LOGGER.info(f'Extracted {file_count} members ({total_size} bytes): {self.filesdir}')
        self.extracted = True

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
    def json(self):
        self.LOGGER.debug(f'Generating JSON for {self.name}')
        return {
            'name': self.name,
            'sosreport': self.sosreport.name,
            'datetime': self.isodate,
            'hostname': self.hostname,
            'machineid': self.machineid,
            'case': self.case,
            **self.meta,
        }

    @cached_property
    def reductions(self):
        return Reductions(self, self.config.get('reductions'))
