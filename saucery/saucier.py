#!/usr/bin/python

from functools import cached_property
from pathlib import Path

from . import SauceryBase
from .grocery import Grocery


class Saucier(SauceryBase):
    DEFAULTS = {
        'max_age': '90 days',
    }

    @classmethod
    def CONFIG_SECTION(cls):
        return 'saucier'

    @cached_property
    def grocery(self):
        return Grocery(self)

    @property
    def max_age(self):
        return self.config.get('max_age')

    @cached_property
    def shelves(self):
        return self.config.get('shelves', '').split()

    def browse_new(self):
        for shelf in self.shelves:
            self.LOGGER.debug(f'Browsing shelves: {shelf}')
            for item in self.grocery.browse(shelf):
                self.LOGGER.debug(f'Browsing item: {item}')
                if not self.saucery.sosreport(Path(item).name).exists():
                    yield item
