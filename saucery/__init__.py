#!/usr/bin/python3

import io
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
from logging import FileHandler
from logging import Formatter
from pathlib import Path
from threading import Lock

from .lookup import ConfigLookup


class SauceryBase(ABC):
    LOGGER = logging.getLogger(__name__)
    SOSREPORT_REGEX = re.compile(r'(?i)(?P<name>sosreport-.*)\.(?P<ext>tar(?:\.(?P<compression>(xz|gz|bz2)))?)$')
    DEFAULT_SAUCERY_DIR = '/saucery'
    DEFAULT_CONFIG_FILE = 'saucery.conf'
    DEFAULTS = {}

    @classmethod
    def CONFIG_SECTION(cls):
        return cls.__name__.lower()

    @classmethod
    def __init_subclass__(cls, **kwargs):
        name = cls.__name__.lower()
        attr = f'_{name}'
        prop = cached_property(lambda self: getattr(self, attr, cls(instance=self)))
        prop.__set_name__(SauceryBase, name)
        # This allows all subclasses to access other instances by 'self.CLASSNAME',
        # for example a grocer instance can access the saucery with 'self.saucery'
        setattr(SauceryBase, name, prop)

    def __init__(self, *, instance=None, **kwargs):
        super().__init__()
        if instance:
            setattr(self, f'_{instance.__class__.__name__}', instance)
            kwargs = ChainMap(kwargs, instance.kwargs)
        self.kwargs = kwargs
        self.setup_logging()
        self.log_dry_run()

    @property
    def saucerydir(self):
        path = Path(self.kwargs.get('saucery') or self.DEFAULT_SAUCERY_DIR)
        if not path.exists():
            raise ValueError(f'Saucery location does not exist, please create it: {path}')
        if not path.is_dir():
            raise ValueError(f'Saucery location is not a dir, please fix: {path}')
        return path

    @property
    def configfiles(self):
        usercfgdir = Path(os.getenv('XDG_CONFIG_HOME', '~/.config')).expanduser().resolve() / 'saucery'
        files = [Path(f).expanduser() for f in [self.DEFAULT_CONFIG_FILE, self.kwargs.get('configfile')] if f]
        dirs = [self.saucerydir / 'config', usercfgdir]
        return [d / f for d in dirs for f in files]

    @property
    def dry_run(self):
        return self.kwargs.get('dry_run', False)

    LOGGED_DRY_RUN = False
    def log_dry_run(self):
        if SauceryBase.LOGGED_DRY_RUN:
            return
        SauceryBase.LOGGED_DRY_RUN = True
        if self.dry_run:
            msg = 'DRY-RUN mode'
            if int(self.dry_run or 0) > 1:
                msg += ' (NO file logging)'
            elif self.kwargs.get('logname'):
                msg += ' (with file logging)'
            self.LOGGER.info(msg)

    LOGGING_SETUP = False
    def setup_logging(self):
        if SauceryBase.LOGGING_SETUP:
            return
        SauceryBase.LOGGING_SETUP = True
        name = self.kwargs.get('logname')
        if not name:
            return
        if int(self.dry_run or 0) > 1:
            return
        formatter = self._log_fmt()
        permanent = self._permanent_log_handler(name)
        timestamped = self._timestamped_log_handler(name)
        if permanent:
            if formatter:
                permanent.setFormatter(formatter)
            logging.getLogger().addHandler(permanent)
        if timestamped:
            if formatter:
                timestamped.setFormatter(formatter)
            logging.getLogger().addHandler(timestamped)

    def _log_path(self, key, name):
        path = self.configsection('logging').get(key)
        if not path:
            return None
        path = Path(path)
        if not path.exists():
            path.mkdir()
        path = path / name
        if not path.suffix:
            path = path.with_suffix('.txt')
        return path

    def _log_fmt(self):
        fmt = self.configsection('logging').get('fmt')
        if not fmt:
            return None
        datefmt = self.configsection('logging').get('datefmt')
        return Formatter(fmt=fmt, datefmt=datefmt)

    def _permanent_log_handler(self, name):
        path = self._log_path('permanent_path', name)
        if not path:
            return None
        return FileHandler(path, mode='a', encoding='utf-8', delay=True)

    def _timestamped_log_handler(self, name):
        path = self._log_path('timestamped_path', name)
        if not path:
            return None
        suffix = path.suffix
        path = path.with_suffix(f'.{datetime.now().isoformat()}{suffix}')
        return FileHandler(path, mode='w', encoding='utf-8', delay=True)

    @cached_property
    def configparser(self):
        configparser = ConfigParser(defaults=self.DEFAULTS)
        configparser.read(self.configfiles)
        return configparser

    @lru_cache
    def configsection(self, section):
        with suppress(DuplicateSectionError):
            self.configparser.add_section(section)
        return ConfigLookup(section, self.configparser[section])

    def dumpconfig(self):
        buf = io.StringIO()
        self.configparser.write(buf)
        return buf.getvalue()

    @property
    def config(self):
        return self.configsection(self.CONFIG_SECTION())

    def lookup(self, name, **kwargs):
        return self.configsection(name).lookup(**kwargs)


class Saucery(SauceryBase):
    @cached_property
    def sosdir(self):
        path = self.saucerydir / 'sos'
        if not path.is_dir():
            if not self.dry_run:
                path.mkdir()
        return path

    @property
    def sauceryreport(self):
        return self.saucery / 'sauceryreport.json'

    @property
    def sosreports(self):
        return [self.sosreport(s)
                for s in self.sosdir.iterdir()
                if s.is_file() and self.SOSREPORT_REGEX.match(s.name)]

    def _sosreport_path(self, sosreport):
        if isinstance(sosreport, SOS):
            return sosreport.sosreport
        return self.sosdir / sosreport

    def sosreport(self, sosreport):
        path = self._sosreport_path(sosreport)
        if not str(path.resolve()).startswith(str(self.sosdir.resolve())):
            raise ValueError(f'Sosreports must be located under {self.sosdir}: invalid location {path}')

        if isinstance(sosreport, SOS):
            return sosreport
        return SOS(self, sosreport=path)

    JSON_LOCK = Lock()

    def create_json(self):
        self.LOGGER.info(f'Creating JSON index {self.sauceryreport}')
        if self.dry_run:
            return

        with self.JSON_LOCK, tempfile.TemporaryDirectory(dir=self.sauceryreport.parent) as tmpdir:
            tmpfile = Path(tmpdir) / 'tmpfile'
            tmpfile.write_text(json.dumps([s.json for s in self.sosreports], indent=2, sort_keys=True))
            tmpfile.rename(self.sauceryreport)


class SOSMetaProperty(property):
    def __new__(cls, name, valuetype=str):
        if valuetype == bool:
            cls = BoolSOSMetaProperty
        return super().__new__(cls)

    def __init__(self, name, valuetype=str):
        self.name = name
        self.valuetype = valuetype
        super().__init__(self.read, self.write, self.unlink)

    def path(self, sos):
        return sos.workdir / self.name

    def read(self, sos):
        with suppress(FileNotFoundError, ValueError):
            return self.valuetype(self.path(sos).read_text().strip())
        return self.valuetype()

    def write(self, sos, value):
        if not sos.dry_run:
            sos.create_workdir()
            value = str(value or '')
            if value and '\n' not in value:
                value += '\n'
            self.path(sos).write_text(value)

    def unlink(self, sos):
        if not sos.dry_run:
            self.path(sos).unlink(missing_ok=True)


class BoolSOSMetaProperty(SOSMetaProperty):
    def __init__(self, name, valuetype=bool):
        super().__init__(name, str)

    def read(self, sos):
        return super().read(sos) == 'True'

    def write(self, sos, value):
        if value is None:
            self.unlink(sos)
        else:
            super().write(sos, str(value == True))


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

    def create_workdir(self):
        if not self.workdir.is_dir():
            self.workdir.mkdir(parents=True, exist_ok=False)
            self.workdir.chmod(0o755)

    @property
    def metaproperties(self):
        return self.config.get('metaproperties', '').split()

    @cached_property
    def meta(self):
        class SOSMeta(object):
            __slots__ = self.metaproperties
            workdir = self.workdir
            dry_run = self.dry_run
            create_workdir = self.create_workdir
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

        self.create_workdir()

        self.extracted = False
        file_list = ''
        file_count = 0
        total_size = 0
        try:
            with tempfile.TemporaryDirectory(dir=self.workdir) as tmpdir:
                with tarfile.open(self.sosreport) as tar:
                    for m in tar.getmembers():
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
                    raise ValueError(f'No files found in sosreport')
                if len(topfiles) > 1:
                    raise ValueError(f'sosreport contains multiple top-level directories')
                # Rename the top-level 'sosreport-...' dir so our files/ dir contains the content
                topfiles[0].rename(self.filesdir)
        except Exception as e:
            self.LOGGER.exception(e)
            raise
        finally:
            self.file_list = file_list
            self.file_count = file_count
            self.total_size = total_size
        self.LOGGER.debug(f'Extracted {self.file_count} members for {self.total_size} bytes: {self.filesdir}')
        self.extracted = True

    hotsos_yaml = SOSMetaProperty('hotsos.yaml')

    def sear(self, *, resear=False):
        if not self.filesdir.exists() or not self.extracted:
            self.LOGGER.error(f"Can't run HotSOS, sosreport not extracted: {self.filesdir}")
            return

        if self.hotsos_yaml and not resear:
            self.LOGGER.info(f'Already seared, not running HotSOS')
            return

        self.LOGGER.info(f'HotSOS: {self.filesdir}')
        if self.dry_run:
            return

        cmd = ['hotsos', '--all-logs']
        cmd += ['--max-parallel-tasks', str(len(os.sched_getaffinity(0)))]
        cmd += [str(self.filesdir)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, encoding='utf-8')
        self.hotsos_yaml = result.stdout

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
