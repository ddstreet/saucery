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
                try:
                    if not self.sosreport(item).exists():
                        yield item
                except ValueError as e:
                    self.LOGGER.error(e)

    @property
    def sosreports(self):
        yield from self.saucery.sosreports

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
            extraction = Thread(target=sos.extract)
            extraction.start()
            if sear:
                searing = Thread(target=lambda: extraction.join() or sos.sear())
                searing.start()
