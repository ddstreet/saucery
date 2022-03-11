#!/usr/bin/python3

import logging
import os
import shutil
import tarfile
import tempfile

from contextlib import suppress
from datetime import datetime
from functools import cached_property
from pathlib import Path


class SOSMetaProperty(property):
    def __init__(self, name):
        self.name = name
        super().__init__(self.read, self.write, self.unlink)

    def metafile(self, sos):
        return sos.workdir / self.name

    def read(self, sos):
        with suppress(FileNotFoundError):
            return self.metafile(sos).read_text().strip()
        return None

    def write(self, sos, value):
        if sos.dry_run:
            return

        # unlink if no value
        if not value:
            self.unlink(sos)
            return

        if not sos.workdir.is_dir():
            sos.workdir.mkdir(parents=True, exist_ok=False)
            sos.workdir.chmod(0o755)
        self.metafile(sos).write_text(f'{value}\n')

    def unlink(self, sos):
        if sos.dry_run:
            return

        self.metafile(sos).unlink(missing_ok=True)


class SOS(object):
    LOGGER = logging.getLogger(__name__)

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
            raise ValueError(f'Invalid/corrupt tarfile')

    def __init__(self, filename, *, dry_run=False):
        self._sosreport = Path(filename).resolve()
        self.dry_run = dry_run

        # Require sanely named sosreport
        n = self._sosreport.name
        if not (n.lower().startswith('sosreport-') and
                n.lower().endswith(('.tar', '.tar.xz', '.tar.gz', '.tar.bz2'))):
            raise ValueError(f'Invalid sosreport name {n}')

    @property
    def sosreport(self):
        return self._sosreport

    @cached_property
    def name(self):
        n = self.sosreport.name
        if n.lower().endswith(('.xz', '.gz', '.bz2')):
            n = n.rpartition('.')[0]
        return n.rpartition('.')[0]

    @cached_property
    def workdir(self):
        return self.sosreport.parent / self.name

    # Meta-files; these are all in the workdir
    case = SOSMetaProperty('case')
    customerid = SOSMetaProperty('customerid')
    customername = SOSMetaProperty('customername')
    hotsos = SOSMetaProperty('hotsos.json')

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

    def extract(self, *, reextract=False):
        if self.filesdir.exists():
            if reextract:
                self.LOGGER.info(f'Removing existing data at {self.filesdir}')
                if not self.dry_run:
                    shutil.rmtree(self.filesdir)
            else:
                self.LOGGER.info(f'Already extracted, not re-extracting: {self.filesdir}')
                return

        self.LOGGER.info(f'Extracting {self.sosreport.name} to {self.filesdir}')
        if self.dry_run:
            return

        self.workdir.mkdir(parents=True, exist_ok=False)
        self.workdir.chmod(0o755)
        with tempfile.TemporaryDirectory(dir=self.workdir) as tmpdir:
            with tarfile.open(self.sosreport) as tar:
                for m in tar.getmembers():
                    if m.isdev():
                        continue
                    tar.extract(m, path=tmpdir)
                    if m.issym():
                        continue
                    mode = 0o775 if m.isdir() else 0o664
                    (Path(tmpdir) / m.name).chmod(mode)
            topfiles = list(Path(tmpdir).iterdir())
            if len(topfiles) == 0:
                raise ValueError(f'No files found in sosreport')
            if len(topfiles) > 1:
                raise ValueError(f'sosreport contains multiple top-level directories')
            # Rename the top-level 'sosreport-...' dir so our files/ dir contains the content
            topfiles[0].rename(self.filesdir)

    def process(self):
        self.LOGGER.debug(f'Processing {self.sosreport}')
        self.gather_hotsos()

    def gather_hotsos(self):
        if self.dry_run:
            return

        cmd = ['hotsos']
        cmd += ['--json']
        cmd += ['--all-logs']
        cmd += ['--max-parallel-tasks', str(len(os.sched_getaffinity(0)))]
        cmd += [str(self.filesdir)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, encoding='utf-8')
        self.hotsos = result.stdout

    @property
    def datetime(self):
        if self.isodate:
            return datetime(self.isodate)
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
            'case': self.case,
            'customerid': self.customerid,
            'customername': self.customername,
            'datetime': self.isodate,
            'hostname': self.hostname,
            'machineid': self.machineid,
        }
