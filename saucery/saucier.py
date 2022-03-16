#!/usr/bin/python

from functools import cached_property
from pathlib import Path
from threading import Thread

from . import SauceryBase
from .grocery import Grocery


class Saucier(SauceryBase):
    DEFAULTS = {
        'max_age': '1 day',
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

    def browse(self, max_age=None):
        max_age = max_age or self.max_age
        for shelf in self.shelves:
            self.LOGGER.debug(f'Browsing shelves: {shelf}')
            for item in self.grocery.browse(shelf, max_age=max_age):
                self.LOGGER.debug(f'Browsing item: {item}')
                if not self.sosreport(Path(item).name).exists():
                    yield item

    @property
    def sosreports(self):
        for sos in self.saucery.sosreports:
            yield sos

    def create_json(self):
        return self.saucery.create_json()

    def buy(self, item, extract=False, sear=False):
        sos = self.sosreport(item)
        self.grocery.buy(item, sos)
        for k, v in self.lookup('sosreport_meta', item=item).items():
            try:
                setattr(sos.meta, k, v)
            except AttributeError:
                self.LOGGER.error(f"Invalid meta attribute '{k}', ignoring.")
        if extract:
            if sear:
                target = lambda: sos.extract() and sos.sear()
            else:
                target = lambda: sos.extract()
            Thread(target=target).start()
