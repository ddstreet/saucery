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
from functools import cached_property
from pathlib import Path

from . import SauceryBase
from .lookup import ConfigLookup


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

    def _browse_isdir(self, stat):
        return stat.st_size is None

    def _browse_isfile(self, stat):
        return not self._browse_isdir(stat)

    def _browse(self, paths, match, path=Path('.')):
        self.LOGGER.debug(f'Browsing {path}/{match}')
        entries = self.sftp.listdir_attr(path=str(path))
        if not paths:
            for e in entries:
                if self._browse_isfile(e) and re.match(match, e.filename):
                    self.LOGGER.debug(f'Browsed to {path / e.filename}')
                    yield str(path / e.filename)
        else:
            for e in entries:
                if self._browse_isdir(e) and re.match(match, e.filename):
                    yield from self._browse(paths[1:], paths[0], path / e.filename)

    def browse(self, shelves):
        '''Browse.

        The 'shelves' value must be a str representing the specific path to browse.
        It will be first split by '/', and each path before the final matched to
        dirs on the server. The final path is matched to files in the preceding
        dirs.

        This will use python regex matching for each entry in the path.

        Returns an iterator of all full paths matching the 'shelves' value, or [].
        '''
        paths = shelves.lstrip('/').split('/')
        try:
            yield from self._browse(paths[1:], paths[0])
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
                return self.sftp.getfo(item, dest, callback=self.progress)

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

    @cached_property
    def shelf_lookup(self):
        return ConfigLookup(self.config, 'shelf')

    def item_shelf(self, item):
        shelves = self.shelf_lookup.lookup(item).values()
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
