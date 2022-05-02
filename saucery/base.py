#!/usr/bin/python3

import argparse
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
from logging import FileHandler
from logging import Formatter
from pathlib import Path

from .lookup import ConfigLookup


class SauceryBase(ABC):
    LOGGER = logging.getLogger(__name__)
    SOSREPORT_REGEX = re.compile(r'(?i)'
                                 r'(?P<name>sosreport-(?P<hostname>.+?)(?:-(?P<case>\d+)-(?P<date>\d{4}-\d{2}-\d{2})-(?P<hash>\w{7}))?)'
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

    @classmethod
    def parse(cls, *, parser=None, actions=None, args=None):
        if not parser:
            parser = argparse.ArgumentParser()
            actions = None
        if not actions:
            actions = parser.add_mutually_exclusive_group()
        actions.add_argument('--dumpconfig', action='store_true',
                             help='Show configuration')
        parser.add_argument('--saucery', help='Location of saucery')
        parser.add_argument('--configfile', help='Config file')
        parser.add_argument('-n', '--dry-run',
                            action='count',
                            help='Dry-run, do not perform actions (use twice to stop file logging also)')
        loglevel = parser.add_mutually_exclusive_group()
        loglevel.add_argument('-q', '--quiet', dest='loglevel', const=logging.WARNING,
                              action='store_const',
                              help='Suppress info messages')
        loglevel.add_argument('-v', '--verbose', dest='loglevel', const=logging.DEBUG,
                              action='store_const',
                              help='Show debug messages')
        loglevel.add_argument('--loglevel', help=argparse.SUPPRESS)
        parser.add_argument('--logname', help=argparse.SUPPRESS)
        opts = parser.parse_args(args)

        logging.basicConfig(level=opts.loglevel or logging.INFO, format='%(message)s')

        self = cls(saucery=opts.saucery,
                   configfile=opts.configfile,
                   dry_run=opts.dry_run,
                   logname=opts.logname)

        self.LOGGER.debug(f'params: {vars(opts)}')

        if opts.dumpconfig:
            self.LOGGER.info(self.dumpconfig())

        return (self, opts)
