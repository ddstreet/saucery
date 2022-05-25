#!/usr/bin/python3

import io
import logging
import os

from abc import ABC
from collections import ChainMap
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from functools import cached_property
from functools import lru_cache
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SauceryBase(ABC):
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
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if instance:
            setattr(self, f'_{instance.__class__.__name__}', instance)
            kwargs = ChainMap(kwargs, instance.kwargs)
        self.kwargs = kwargs

    @property
    def configfiles(self):
        xdg_config_home = os.getenv('XDG_CONFIG_HOME', '~/.config')
        files = [Path(xdg_config_home).expanduser().resolve() / 'saucery' / 'saucery.conf']
        customcfg = self.kwargs.get('configfile')
        if customcfg:
            files.append(Path(customcfg).expanduser().resolve())
        return files

    @property
    def dry_run(self):
        return self.kwargs.get('dry_run', False)

    @cached_property
    def configparser(self):
        configparser = ConfigParser()
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

    @cached_property
    def config(self):
        return ChainMap(self.kwargs,
                        self.environconfig,
                        self.configsection(self.CONFIG_SECTION()),
                        self.defaultconfig)

    @property
    def environconfig(self):
        prefix = 'SAUCERY_'
        plen = len(prefix)
        return {k[plen:].lower(): v for k, v in os.environ.items()
                if k.startswith(prefix) and len(k) > plen}

    @property
    def defaultconfig(self):
        return {}
