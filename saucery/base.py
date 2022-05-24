#!/usr/bin/python3

import io
import logging
import os
import re

from abc import ABC
from collections import ChainMap
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from datetime import datetime
from functools import cached_property
from functools import lru_cache
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SauceryBase(ABC):
    SOSREPORT_REGEX = re.compile(r'(?i)'
                                 r'(?P<name>sosreport-(?P<hostname>.+?)(?:-(?P<case>\d+)-(?P<date>\d{4}-\d{2}-\d{2})-(?P<hash>\w{7}))?)' # noqa
                                 r'\.(?P<ext>tar(?:\.(?P<compression>(xz|gz|bz2)))?)$')
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
        # This allows all subclasses to access other instances by 'self.CLASSNAME'
        setattr(SauceryBase, name, prop)

    def __init__(self, *, instance=None, **kwargs):
        super().__init__()
        if instance:
            setattr(self, f'_{instance.__class__.__name__}', instance)
            kwargs = ChainMap(kwargs, instance.kwargs)
        self.kwargs = kwargs

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
        xdg_config_home = os.getenv('XDG_CONFIG_HOME', '~/.config')
        usercfgdir = Path(xdg_config_home).expanduser().resolve() / 'saucery'
        files = [Path(f).expanduser()
                 for f in [self.DEFAULT_CONFIG_FILE, self.kwargs.get('configfile')]
                 if f]
        dirs = [self.saucerydir / 'config', usercfgdir]
        return [d / f for d in dirs for f in files]

    @property
    def dry_run(self):
        return self.kwargs.get('dry_run', False)

    @cached_property
    def configparser(self):
        configparser = ConfigParser(defaults=self.DEFAULTS)
        configparser.read(self.configfiles)
        return configparser

    @lru_cache
    def configsection(self, section):
        with suppress(DuplicateSectionError):
            self.configparser.add_section(section)
        return self.configparser[section]

    def dumpconfig(self):
        buf = io.StringIO()
        self.configparser.write(buf)
        return buf.getvalue()

    @property
    def config(self):
        return self.configsection(self.CONFIG_SECTION())
