#!/usr/bin/python3

import json
import logging
import os
import re
import subprocess
import tempfile

from abc import ABC
from abc import abstractmethod
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from functools import cached_property
from pathlib import Path

from .sos import SOS


class SauceryBase(ABC):
    LOGGER = logging.getLogger(__name__)
    DEFAULT_CONFIGDIR = Path(os.getenv('XDG_CONFIG_HOME', '~/.config')).expanduser().resolve() / 'saucery'
    DEFAULT_CONFIGFILES = ['saucery.conf', 'saucier.conf', 'grocery.conf', 'grocer.conf']
    DEFAULTS = {}

    @classmethod
    @abstractmethod
    def CONFIG_SECTION(cls):
        pass

    def __init__(self, configfile=None, **kwargs):
        super().__init__()
        if isinstance(configfile, SauceryBase):
            self.__init__(configfile._configfile, **configfile.kwargs)
        else:
            self._configfile = configfile
            self.kwargs = kwargs

    @property
    def dry_run(self):
        return self.kwargs.get('dry_run', False)

    @cached_property
    def saucery(self):
        return Saucery(self)

    @cached_property
    def config(self):
        config = ConfigParser(defaults=self.DEFAULTS)
        config.read([self.DEFAULT_CONFIGDIR / f
                     for f in self.DEFAULT_CONFIGFILES + [self._configfile]
                     if f])
        section = self.CONFIG_SECTION()
        with suppress(DuplicateSectionError):
            config.add_section(section)
        return config[section]


class Saucery(SauceryBase):
    DEFAULTS = {
        'saucery': '/saucery',
    }
    SOSREPORT_REGEX = re.compile(r'sosreport-.*\.tar(\.[^.]+)?')

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
        filenames = (s.name for s in self.sos.iterdir() if s.is_file())
        yield from (path / n for n in filenames if self.SOSREPORT_REGEX.match)

    def sosreport(self, filename):
        src = self.sos / filename
        if not str(src.resolve()).startswith(str(self.sos.resolve())):
            raise ValueError(f'Sosreports must be located under {self.sos}: invalid location {src}')

        return SOS(src, dry_run=self.dry_run)

    def create_json(self):
        if self.dry_run:
            return

        with tempfile.TemporaryDirectory(dir=self.sauceryreport.parent) as tmpdir:
            tmpfile = Path(tmpdir) / 'tmpfile'
            tmpfile.write_text(json.dumps([self.sosreport(s).json for s in self.sosreports],
                                          indent=2, sort_keys=True))
            tmpfile.rename(self.sauceryreport)
