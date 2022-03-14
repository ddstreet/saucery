#!/usr/bin/python

from functools import cached_property
from pathlib import Path
from threading import Thread

from . import SauceryBase
from .grocery import Grocery
from .lookup import ConfigLookup


class Saucier(SauceryBase):
    DEFAULTS = {
        'max_age': '90 days',
    }

    @classmethod
    def CONFIG_SECTION(cls):
        return 'saucier'

    def sosreport(self, name):
        return self.saucery.sosreport(Path(name).name)

    @property
    def max_age(self):
        return self.config.get('max_age')

    @cached_property
    def shelves(self):
        return self.config.get('shelves', '').split()

    def browse_grocery(self, only_new=True):
        for shelf in self.shelves:
            self.LOGGER.debug(f'Browsing shelves: {shelf}')
            for item in self.grocery.browse(shelf):
                self.LOGGER.debug(f'Browsing item: {item}')
                if not only_new or not self.sosreport(Path(item).name).exists():
                    yield item

    def browse(self):
        for sos in self.saucery.sosreports:
            yield sos

    @cached_property
    def meta_lookup(self):
        return ConfigLookup(self.config, 'meta')

    def buy(self, item):
        sos = self.sosreport(item)
        self.grocery.buy(item, sos)
        results = self.meta_lookup.lookup(item)
        if results:
            for k, v in results.items():
                try:
                    setattr(sos.meta, k, v)
                except AttributeError:
                    self.LOGGER.error(f"Invalid meta attribute '{k}', ignoring.")
        Thread(target=sos.extract).start()
