#!/usr/bin/python3

import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

from abc import ABC
from abc import abstractmethod
from collections import ChainMap
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from datetime import datetime
from functools import cached_property
from functools import lru_cache
from pathlib import Path

from .lookup import ConfigLookup


class SauceryBase(ABC):
    LOGGER = logging.getLogger(__name__)
    SOSREPORT_REGEX = re.compile(r'(?i)(?P<name>sosreport-.*)\.(?P<ext>tar(?:\.(?P<compression>(xz|gz|bz2)))?)$')
    DEFAULT_CONFIGDIR = Path(os.getenv('XDG_CONFIG_HOME', '~/.config')).expanduser().resolve() / 'saucery'
    DEFAULT_CONFIGFILES = ['saucery.conf', 'saucier.conf', 'grocery.conf', 'grocer.conf']
    DEFAULTS = {}

    @classmethod
    @abstractmethod
    def CONFIG_SECTION(cls):
        pass

    @classmethod
    def __init_subclass__(cls, **kwargs):
        name = cls.__name__.lower()
        attr = f'_{name}'
        prop = cached_property(lambda self: getattr(self, attr, cls(self)))
        prop.__set_name__(SauceryBase, name)
        setattr(SauceryBase, name, prop)

    def __init__(self, configfile_or_instance=None, **kwargs):
        super().__init__()
        if isinstance(configfile_or_instance, SauceryBase):
            setattr(self, f'_{configfile_or_instance.__class__.__name__}', configfile_or_instance)
            kwargs = ChainMap(kwargs, configfile_or_instance.kwargs)
            configfile_or_instance = configfile_or_instance._configfile
        self._configfile = configfile_or_instance
        self.kwargs = kwargs

    @property
    def dry_run(self):
        return self.kwargs.get('dry_run', False)

    @cached_property
    def configparser(self):
        configparser = ConfigParser(defaults=self.DEFAULTS)
        configparser.read([self.DEFAULT_CONFIGDIR / f
                           for f in self.DEFAULT_CONFIGFILES + [self._configfile]
                           if f])
        return configparser

    @lru_cache
    def configsection(self, section):
        with suppress(DuplicateSectionError):
            self.configparser.add_section(section)
        return ConfigLookup(section, self.configparser[section])

    @cached_property
    def config(self):
        return self.configsection(self.CONFIG_SECTION())

    def lookup(self, name, **kwargs):
        return self.configsection(name).lookup(**kwargs)


class Saucery(SauceryBase):
    DEFAULTS = {
        'saucery': '/saucery',
    }

    @classmethod
    def CONFIG_SECTION(cls):
        return 'saucery'

    @cached_property
    def saucery(self):
        path = Path(self.config['saucery'])
        if not path.exists():
            raise ValueError(f'Saucery location does not exist, please create it: {path}')
        if not path.is_dir():
            raise ValueError(f'Saucery location is not a dir, please fix: {path}')

        return path

    @cached_property
    def sos(self):
        path = self.saucery / 'sos'
        if not path.is_dir():
            if self.dry_run:
                self.LOGGER.error('Dry-run mode, but no saucery sos dir')
            else:
                path.mkdir()
        return path

    @property
    def sauceryreport(self):
        return self.saucery / 'sauceryreport.json'

    @property
    def sosreports(self):
        for s in self.sos.iterdir():
            if s.is_file() and self.SOSREPORT_REGEX.match(s.name):
                yield self.sosreport(s)

    def _sosreport_path(self, sosreport):
        if isinstance(sosreport, SOS):
            return sosreport.sosreport
        return self.sos / sosreport

    def sosreport(self, sosreport):
        path = self._sosreport_path(sosreport)
        if not str(path.resolve()).startswith(str(self.sos.resolve())):
            raise ValueError(f'Sosreports must be located under {self.sos}: invalid location {path}')

        if isinstance(sos, SOS):
            return sos
        return SOS(self, sosreport=path)

    def create_json(self):
        if self.dry_run:
            return

        with tempfile.TemporaryDirectory(dir=self.sauceryreport.parent) as tmpdir:
            tmpfile = Path(tmpdir) / 'tmpfile'
            tmpfile.write_text(json.dumps([s.json for s in self.sosreports], indent=2, sort_keys=True))
            tmpfile.rename(self.sauceryreport)


class SOS(SauceryBase):
    @classmethod
    def CONFIG_SECTION(cls):
        return 'sos'

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
        return self.sosreport.exists()

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

    @property
    def metaproperties(self):
        return self.config.get('metaproperties', '').split()

    @cached_property
    def meta(self):
        class SOSMeta(object):
            __slots__ = self.metaproperties
            _sos = self
        for n in self.metaproperties:
            setattr(SOSMeta, n, SOSMetaProperty(n))
        return SOSMeta()

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

        self.workdir.mkdir(parents=True, exist_ok=True)
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
    def base_json(self):
        return {
            'name': self.name,
            'sosreport': self.sosreport.name,
            'datetime': self.isodate,
            'hostname': self.hostname,
            'machineid': self.machineid,
        }

    @property
    def meta_json(self):
        return {name: getattr(self.meta, name) for name in self.metaproperties}

    @property
    def json(self):
        self.LOGGER.debug(f'Generating JSON for {self.name}')
        return {**self.base_json, **self.meta_json}


class SOSMetaProperty(property):
    def __init__(self, name):
        self.name = name
        super().__init__(self.read, self.write, self.unlink)

    def metafile(self, meta):
        return meta._sos.workdir / self.name

    def dry_run(self, meta):
        return meta._sos.dry_run

    def read(self, meta):
        with suppress(FileNotFoundError):
            return self.metafile(meta).read_text().strip()
        return None

    def write(self, meta, value):
        if self.dry_run(meta):
            return

        if value:
            workdir = meta._sos.workdir
            if not workdir.is_dir():
                workdir.mkdir(parents=True, exist_ok=False)
                workdir.chmod(0o755)
            self.metafile(meta).write_text(f'{value}\n')
        else:
            # unlink if no value
            self.unlink(meta)

    def unlink(self, meta):
        if not self.dry_run(meta):
            self.metafile(meta).unlink(missing_ok=True)
