#!/usr/bin/python3

import ast
import dateparser
import logging
import os
import paramiko
import re
import subprocess
import sys

from abc import abstractmethod
from configparser import ConfigParser
from configparser import DuplicateSectionError
from contextlib import suppress
from copy import copy
from datetime import datetime
from datetime import timedelta
from functools import cached_property
from pathlib import Path

from . import SauceryBase


class Grocery(SauceryBase):
    DEFAULTS = {
        'shelflife': '30 days',
    }

    @classmethod
    def CONFIG_SECTION(cls):
        return 'grocery'

    def __init__(self, *args, server=None, username=None, log_remote=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not log_remote:
            logging.getLogger('paramiko').setLevel(logging.CRITICAL)
        self._server = server
        self._username = username

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
    def _sftp(self):
        client = paramiko.client.SSHClient()
        client.load_system_host_keys()
        client.connect(self.server, username=self.username)
        sftp = client.open_sftp()
        sftp._myclient = client
        return sftp

    @property
    def sftp(self):
        try:
            active = self._sftp._myclient.get_transport().is_active()
        except AttributeError:
            active = False
        if not active:
            del self._sftp
        return self._sftp

    def getfo(self, item, dest, callback=None):
        return self.sftp.getfo(item, dest, callback=callback)

    def stat(self, item):
        if item is None:
            return None
        if not isinstance(item, str):
            return item
        with suppress(FileNotFoundError):
            return self.sftp.stat(item)
        return None

    def _attr(self, item, attr):
        for i in (item, self.stat(item)):
            if hasattr(i, attr):
                return getattr(i, attr)
        return None

    def size(self, item):
        return self._attr(item, 'st_size')

    def mtime(self, item):
        return self._attr(item, 'st_mtime')

    def exists(self, item):
        return self.stat(item) is not None

    def listdir(self, shelf, attr=False):
        if not self.exists(shelf):
            return []
        listdir = self.sftp.listdir_attr if attr else self.sftp.listdir
        return listdir(path=shelf)

    def create_shelf(self, shelf):
        self.LOGGER.debug(f'mkdir: {shelf}')
        try:
            if not self.dry_run:
                if not self.exists(shelf):
                    self.sftp.mkdir(shelf)
        except IOError:
            self.LOGGER.error(f'Failed to mkdir {shelf}')
            return False
        return True

    def _shelve(self, item, shelf, dest):
        self.LOGGER.info(f'{item} -> {dest}')
        if self.create_shelf(shelf):
            if not self.dry_run:
                self.sftp.rename(item, dest)

    def shelve(self, item, shelf, replace=False):
        shelf = self.manager.micromanage(shelf)
        dest = str(Path(shelf) / Path(item).name)
        if self.exists(dest):
            if replace:
                self.LOGGER.warning(f'REPLACING existing file {dest}')
            else:
                raise FileExistsError(dest)
        self._shelve(item, shelf, dest)

    def shelf_items(self, shelf):
        if not self.exists(shelf):
            return []
        yield from (str(Path(shelf) / item) for item in self.listdir(shelf))

    def is_shelf(self, item):
        return self.size(item) is None

    def is_item(self, item):
        return not self.is_shelf(item)

    def _browse(self, paths, match, path=Path('.'), age=None):
        self.LOGGER.debug(f'Browsing {path}/{match}')
        entries = self.listdir(str(path), attr=True)
        for e in entries:
            if not re.match(match, e.filename):
                continue
            if not self.is_fresh(e, age):
                continue
            newpath = path / e.filename
            if paths and self.is_shelf(e):
                yield from self._browse(paths[1:], paths[0], newpath, age=age)
            elif not paths and self.is_item(e):
                self.LOGGER.debug(f'Browsed to {newpath}')
                yield str(newpath)

    def browse(self, shelves, shelflife=None):
        '''Browse.

        The 'shelves' value must be a str representing the specific path to browse.
        It will be first split by '/', and each path before the final matched to
        dirs on the server. The final path is matched to files in the preceding
        dirs.

        If 'shelflife' is not provided, this grocery's configured shelflife is used.
        If provided, it must be a timedelta, (tz-naive) datetime, or str.

        This will use python regex matching for each entry in the path.

        Returns an iterator of all full paths matching the 'shelves' value, or [].
        '''
        paths = shelves.lstrip('/').split('/')
        try:
            yield from self._browse(paths[1:], paths[0], age=self.parse_age(shelflife))
        except IndexError:
            return []

    def progress(self, n, total):
        if not sys.stderr.isatty():
            return
        percent = (n * 100) // total
        print(f'\r{percent:>3}%', end='\n' if n == total else '')

    def buy(self, item, sos):
        self.LOGGER.info(f'{item} -> {sos}')
        if not self.dry_run:
            with sos.sosreport.open('wb') as dest:
                return self.getfo(item, dest, callback=self.progress)

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

    def is_fresh(self, item, shelflife=None):
        shelflife = shelflife or self.shelflife
        if not shelflife:
            return True
        return self.age(item) < self.parse_age(shelflife)

    def age(self, item):
        mtime = self.mtime(item)
        if not mtime:
            return None
        return self.parse_age(datetime.fromtimestamp(mtime))

    def parse_age(self, age):
        log_age = age
        if not age:
            return None
        if isinstance(age, str):
            age = dateparser.parse(f'{age} ago')
        if isinstance(age, datetime):
            age = datetime.now() - age
        if isinstance(age, timedelta):
            return age
        self.LOGGER.warning(f'Invalid age, ignoring: {log_age}')
        return None

    @cached_property
    def shelflife(self):
        return self.parse_age(self.config['shelflife'])


class Grocer(SauceryBase):
    @classmethod
    def CONFIG_SECTION(cls):
        return 'grocer'

    def stock(self):
        for item in self.grocery.deliveries:
            self.stock_item(item)

    def stock_item(self, item):
        shelf = self.item_shelf(Path(item).name)
        if shelf:
            try:
                self.grocery.shelve(item, shelf)
                self.stock_actions(item, shelf)
            except FileExistsError:
                dest = Path(shelf) / Path(item).name
                self.LOGGER.info(f'Not replacing existing file {dest}')
        else:
            self.grocery.shelve(item, self.grocery.discounts_shelf, replace=True)

    def stock_actions(self, item, shelf):
        if self.dry_run:
            return
        for v in self.lookup('stock_actions', item=item, shelf=shelf).values():
            self.LOGGER.info(v)

    def dispose(self):
        for item in self.grocery.discounts:
            if not self.grocery.is_fresh(item):
                self.LOGGER.info(f'Disposing of expired file {item} with age {self.grocery.age(item)}')
                self.dispose_item(item)
            else:
                self.LOGGER.debug(f'Leaving unexpired file {item} with age {self.grocery.age(item)}')

    def dispose_item(self, item):
        self.grocery.shelve(item, self.grocery.expired_shelf, replace=True)

    def item_shelf(self, item):
        shelves = self.lookup('item_shelf', item=item).values()
        if not shelves:
            return None
        return Path('').joinpath(*shelves)


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
