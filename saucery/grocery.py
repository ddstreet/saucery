#!/usr/bin/python3

import ast
import dateparser
import logging
import os
import paramiko
import re
import subprocess

from abc import abstractmethod
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from copy import copy
from datetime import datetime
from functools import cached_property
from pathlib import Path

from . import SauceryBase


class Grocery(SauceryBase):
    DEFAULTS = {
        'shelflife': '30 days',
        'deliveries': 'uploads',
        'discounts': 'triage',
        'expired': 'trash',
    }

    @classmethod
    def CONFIG_SECTION(cls):
        return 'grocery'

    def __init__(self, *args, server=None, username=None, log_sftp=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_sftp = log_sftp
        self._server = server
        self._username = username

    @cached_property
    def manager(self):
        return Manager(self)

    @cached_property
    def grocer(self):
        grocername = self.config.get('grocer')
        if not grocername:
            raise ValueError('No config found for Grocer')
        grocercls = Grocer.GROCERS.get(grocername)
        if not grocercls:
            raise ValueError(f'No Grocer class found for {grocername}')
        return grocercls(self)

    @property
    def server(self):
        try:
            return self._server or self.config['server']
        except KeyError:
            raise RuntimeError('No configuration found for remote server')

    @property
    def username(self):
        try:
            return self._username or self.config['username']
        except KeyError:
            raise RuntimeError('No configuration found for username')

    @cached_property
    def sftp(self):
        if not self.log_sftp:
            logging.getLogger('paramiko').setLevel(logging.CRITICAL)
        client = paramiko.client.SSHClient()
        client.load_system_host_keys()
        client.connect(self.server, username=self.username)
        return client.open_sftp()

    def shelf_items(self, shelf):
        if not shelf:
            return []
        try:
            self.sftp.stat(shelf)
        except FileNotFoundError:
            return []
        yield from (str(Path(shelf) / item) for item in self.sftp.listdir(path=shelf))

    def _listdir(self, path, match=None):
        match = match or '.'
        try:
            self.sftp.stat(path)
        except FileNotFoundError:
            return []
        return [str(Path(path) / f)
                for f in self.sftp.listdir(path=path) if re.match(match, f)]

    def aisles(self, match=None):
        return self._listdir('', match)

    def sections(self, aisle, match=None):
        return self._listdir(aisle, match)

    def shelves(self, section, match=None):
        return self._listdir(section, match)

    @property
    def deliveries_shelf(self):
        return self.config.get('deliveries')

    @property
    def discounts_shelf(self):
        return self.config.get('discounts')

    @property
    def expired_shelf(self):
        return self.config.get('expired')

    @property
    def deliveries(self):
        yield from self.shelf_items(self.deliveries_shelf)

    @property
    def discounts(self):
        yield from self.shelf_items(self.discounts_shelf)

    @property
    def expired(self):
        yield from self.shelf_items(self.expired_shelf)

    def discount(self, item):
        self.shelve(item, self.discounts_shelf, replace=True)

    def expire(self, item):
        self.shelve(item, self.expired_shelf, replace=True)

    def age(self, item):
        mtime = self.sftp.stat(item).st_mtime
        return datetime.now() - datetime.fromtimestamp(mtime)

    @property
    def shelflife(self):
        shelflife = self.config['shelflife']
        if not shelflife.lower().endswith(' ago'):
            shelflife += ' ago'
        return datetime.now() - dateparser.parse(shelflife)

    def shelve(self, item, shelf, replace=False):
        shelf = self.manager.micromanage(shelf)
        dest = str(Path(shelf) / Path(item).name)
        with suppress(FileNotFoundError):
            self.sftp.stat(dest)
            if replace:
                self.LOGGER.warning(f'REPLACING existing file {dest}')
            else:
                raise FileExistsError(dest)
        try:
            self.sftp.stat(shelf)
        except FileNotFoundError:
            try:
                self.LOGGER.debug(f'mkdir: {shelf}')
                if not self.dry_run:
                    self.sftp.mkdir(shelf)
            except IOError:
                self.LOGGER.error(f'Failed to mkdir {shelf}')
                return
        self.LOGGER.info(f'{item} -> {dest}')
        if not self.dry_run:
            self.sftp.rename(item, dest)


class Grocer(SauceryBase):
    GROCERS = {}

    @classmethod
    def CONFIG_SECTION(cls):
        return 'grocer'

    @classmethod
    def __init_subclass__(cls, **kwargs):
        cls.GROCERS[cls.__name__] = cls

    def __init__(self, grocery, **kwargs):
        super().__init__(grocery, **kwargs)
        self.grocery = grocery

    @abstractmethod
    def item_shelf(self, item):
        pass

    def stock(self):
        for item in self.grocery.deliveries:
            self.stock_item(item)

    def stock_item(self, item):
        shelf = self.item_shelf(Path(item).name)
        if shelf:
            try:
                self.grocery.shelve(item, shelf)
            except FileExistsError:
                dest = Path(shelf) / Path(item).name
                self.LOGGER.info(f'Not replacing existing file {dest}')
        else:
            self.grocery.discount(item)

    def dispose(self):
        for item in self.grocery.discounts:
            age = self.grocery.age(item)
            if age > self.grocery.shelflife:
                self.LOGGER.info(f'Disposing of expired file {item} with age {age}')
                self.dispose_item(item)
            else:
                self.LOGGER.debug(f'Leaving unexpired file {item} with age {age}')

    def dispose_item(self, item):
        self.grocery.expire(item)


class LookupGrocer(Grocer):
    def lookup(self, key, formatmap):
        self.LOGGER.debug(f"No value for '{key}'")
        return None

class ConstGrocer(LookupGrocer):
    '''Grocer that performs lookupins using the direct value.

    The lookup key must use the suffix '_const'.

    If the key is found in the config, its value is used.

    If the key is not found in the config, None is returned.
    '''
    def lookup_const(self, key, formatmap):
        key = f'{key}_const'
        value = self.config.get(key)
        self.LOGGER.debug(f"lookup_const '{key}': {value}")
        return value

    def lookup(self, key, formatmap):
        value = self.lookup_const(key, formatmap)
        if value is None:
            return super().lookup(key, formatmap)
        return value


class SubprocessGrocer(LookupGrocer):
    '''Grocer that performs lookups using subprocess call.

    The lookup key must use the suffix '_subprocess'. The value must be a
    python list, which will be passed directly to subprocess.

    The list string will be evaluated with ast.literal_eval(), and then each
    string in the list will be formatted using the format map, so any literal
    { or } characters in the command must be doubled (i.e. {{ or }}).

    The result returncode should be 0 if successfully looked up or if
    no result was found. The result returncode should be nonzero if there
    was a failure and stderr should include the text of the failure, which
    will be logged, and None returned.

    On success, the subprocess stdout should be the str result, or if there was no
    result found, the stdout should be empty.
    '''
    @property
    def subprocess_timeout(self):
        return self.config.get('subprocess_timeout', 30)

    def lookup_subprocess(self, key, formatmap):
        key = f'{key}_subprocess'
        cmd = self.config.get(key)
        self.LOGGER.debug(f"lookup_subprocess '{key}': {cmd}")
        if not cmd:
            return None
        cmd = ast.literal_eval(cmd)
        if not isinstance(cmd, list):
            self.LOGGER.error(f'Invalid lookup cmd (not a list): {cmd}')
            return None
        cmd = [c.format(**formatmap) for c in cmd]
        try:
            result = subprocess.run(cmd, encoding='utf-8',
                                    timeout=self.subprocess_timeout,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            self.LOGGER.error(f'Timed out waiting for lookup cmd')
            return None
        if result.returncode != 0:
            self.LOGGER.error(f'Error running lookup cmd: {result.stderr}')
            return None
        return result.stdout

    def lookup(self, key, formatmap):
        value = self.lookup_subprocess(key, formatmap)
        if value is None:
            return super().lookup(key, formatmap)
        return value


class PythonGrocer(LookupGrocer):
    '''Grocer that performs lookups using python.

    The lookup key must use the suffix '_python'. The value must python
    code that will be passed directly to eval(). Copies of the running
    globals() and locals() will be stored by this class instance and passed
    to each call to eval.

    The string will first be formatted using the format map, so any literal
    { or } characters in the command must be doubled (i.e. {{ or }}).

    On failure, the python code should raise an Exception, which will be caught
    and the exception error logged, and None will be returned for this lookup.

    On success, the return value of the call to eval() should be the str-type result.

    If no error occurred, but no result was found, the return value should be ''.
    '''
    @cached_property
    def globals(self):
        return copy(globals())

    @cached_property
    def locals(self):
        return copy(locals())

    def lookup_python(self, key, formatmap):
        key = f'{key}_python'
        cmd = self.config.get(key)
        self.LOGGER.debug(f"lookup_python '{key}': {cmd}")
        if not cmd:
            return None
        cmd = cmd.format(**formatmap)
        try:
            return eval(cmd, self.globals, self.locals)
        except Exception as e:
            self.LOGGER.error(f'Error running lookup cmd: {e}')
            return None

    def lookup(self, key, formatmap):
        value = self.lookup_python(key, formatmap)
        if value is None:
            return super().lookup(key, formatmap)
        return value


class AisleSectionShelfGrocer(SubprocessGrocer, PythonGrocer, ConstGrocer):
    '''AisleSectionShelfGrocer.

    Use python and/or subprocess cmds, or const values, from our config file
    to lookup what specific shelf this item belongs on.

    The lookup order defaults to most-specific first, meaning 'shelf'
    then 'section' and then 'aisle'. This order may be adjusted with the
    'lookup_order' config, which should be a space and/or command separated
    list of key names. At least one of the default key names must be included.
    Arbitrary keys may be looked up as well, for use with later lookups.

    Each lookup is provided a format map, which starts with the special key
    'item' that is set to the str value of the item name. After each lookup,
    the lookup key and its looked-up value are placed into the format map.

    If any lookup results in None, the process ends and None is returned.

    After all lookups are complete, if the combined path of the values of
    'aisle'/'section'/'shelf' results in a location other than '.',
    it is returned; otherwise None is returned.
    '''
    DEFAULT_LOOKUP_ORDER = ['shelf', 'section', 'aisle']

    @cached_property
    def order(self):
        order = [o for o in re.split(r'[ ,]', self.config.get('lookup_order')) if o]
        if order and set(order).isdisjoint(set(self.DEFAULT_LOOKUP_ORDER)):
            self.LOGGER.error(f'Invalid Grocer lookup_order, requires at least one of {",".join(self.DEFAULT_LOOKUP_ORDER)}, ignoring: {",".join(order)}')
            order = None
        return order or self.DEFAULT_LOOKUP_ORDER

    def item_shelf(self, item):
        fmtmap = {'item': item}
        for key in self.order:
            location = self.lookup(key, fmtmap)
            if location is None:
                return None
            fmtmap[key] = location
        self.LOGGER.debug(f'lookup result: {fmtmap}')
        path = str(Path(fmtmap.get('aisle', '')) /
                   fmtmap.get('section', '') /
                   fmtmap.get('shelf', ''))
        if path == '.':
            return None
        return path


class Manager(SauceryBase):
    @classmethod
    def CONFIG_SECTION(cls):
        return 'manager'

    @property
    def snowflakes(self):
        snowflakes = self.config.get('snowflakes')
        if not snowflakes:
            return {}
        snowflakes = ast.literal_eval(snowflakes)
        if not isinstance(snowflakes, dict):
            raise ValueError(f'Invalid manager snowflakes, must be dict: {snowflakes}')
        return snowflakes

    def micromanage(self, shelf):
        for snowflake, checkout_aisle in self.snowflakes.items():
            if shelf.startswith(snowflake):
                return shelf.replace(snowflake, checkout_aisle, 1)
        return shelf
