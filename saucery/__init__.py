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
from collections.abc import MutableMapping
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from copy import copy
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

    def lookup(self, section, initial_keys):
        return self.configsection(section).lookup(**initial_keys)


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
        return self.saucerydir / 'sauceryreport.json'

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
        return SOS(instance=self, sosreport=path)

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
    def __new__(cls, name, valuetype=str, **kwargs):
        if valuetype == bool:
            cls = BoolSOSMetaProperty
        return super().__new__(cls)

    def __init__(self, name, valuetype=str, valuelist=False):
        self.name = name
        self.valuetype = valuetype
        self.valuelist = valuelist
        super().__init__(self.read, self.write, self.unlink)

    def path(self, sos):
        return sos.workdir / self.name

    def value(self, strvalue):
        if self.valuelist:
            with suppress(ValueError):
                return [self.valuetype(v) for v in strvalue.split()]
            return []
        with suppress(ValueError):
            return self.valuetype(strvalue)
        return self.valuetype()

    def strvalue(self, value):
        if isinstance(value, list):
            value = ' '.join(map(self.strvalue, value))
        return str(value or '')

    def read(self, sos):
        with suppress(FileNotFoundError):
            return self.value(self.path(sos).read_text().strip())
        return self.value('')

    def write(self, sos, value):
        if not sos.dry_run:
            value = self.strvalue(value)
            if value and '\n' not in value:
                value += '\n'
            path = self.path(sos)
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)

    def unlink(self, sos):
        if not sos.dry_run:
            self.path(sos).unlink(missing_ok=True)


class BoolSOSMetaProperty(SOSMetaProperty):
    def __init__(self, name, valuetype=bool, **kwargs):
        super().__init__(name, valuetype=lambda v: v == 'True', **kwargs)

    def strvalue(self, value):
        return str(value == True)


class SOSMetaDict(MutableMapping):
    def __init__(self, sos, keys):
        super().__init__()
        self._keys = copy(keys)
        class SOSMeta():
            dry_run = sos.dry_run
            workdir = sos.workdir
        for k in keys:
            setattr(SOSMeta, k, SOSMetaProperty(k))
        self.meta = SOSMeta()

    def __getitem__(self, key):
        if key not in self._keys:
            raise KeyError(key)
        return getattr(self.meta, key)

    def __setitem__(self, key, value):
        if key not in self._keys:
            raise KeyError(key)
        setattr(self.meta, key, value)

    def __delitem__(self, key):
        if key not in self._keys:
            raise KeyError(key)
        delattr(self.meta, key)

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)


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

    meta_key = SOSMetaProperty('meta_key')

    @cached_property
    def meta(self):
        keys = self.configsection('sosreport_meta').get('lookup_keys', '').split()
        return SOSMetaDict(self, keys)

    seared = SOSMetaProperty('seared', bool)

    def sear(self, resear=False):
        if not self.filesdir.exists() or not self.extracted:
            self.LOGGER.error(f"Not extracted, can't sear sosreport {self.name}")
            return

        if not self.meta_key:
            self.LOGGER.error(f"No meta key, can't sear sosreport {self.name}")
            return

        if self.seared:
            if resear:
                self.LOGGER.info(f'Re-searing {self.name}')
            else:
                self.LOGGER.info(f'Already seared, not re-searing {self.name}')
                return
        else:
            self.LOGGER.info(f'Searing {self.name}')

        self.seared = False
        initial_keys = {
            'meta_key': self.meta_key,
            'sosreport_files': str(self.filesdir),
        }
        for k, v in self.lookup('sosreport_meta', initial_keys).items():
            self.meta[k] = v
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
            **self.meta,
        }
