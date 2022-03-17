#!/usr/bin/python

import os

from concurrent import futures
from functools import cached_property
from pathlib import Path

from . import SauceryBase
from . import SOS
from .grocery import Grocery


class Saucier(SauceryBase):
    DEFAULTS = {
        'max_age': '1 day',
    }

    @classmethod
    def CONFIG_SECTION(cls):
        return 'saucier'

    def sosreport(self, name):
        if isinstance(name, SOS):
            return name
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

    def buy(self, item):
        sos = self.sosreport(item)
        self.grocery.buy(item, sos)
        for k, v in self.lookup('sosreport_meta', item=item).items():
            try:
                setattr(sos.meta, k, v)
            except AttributeError:
                self.LOGGER.error(f"Invalid meta attribute '{k}', ignoring.")

    def _sosreports(self, sosreports):
        soses = []
        for s in sosreports:
            try:
                soses.append(self.sosreport(s))
            except ValueError as e:
                self.LOGGER.info(e)
        return soses

    def _parallel(self, sosreports, action, parallel=True, **kwargs):
        sosreports = self._sosreports(sosreports)

        run = lambda s: getattr(s, action)(**kwargs)

        if not parallel:
            for s in sosreports:
                run(s)
            return

        if parallel is True:
            parallel = len(os.sched_getaffinity(0))
        with futures.ThreadPoolExecutor(max_workers=int(parallel)) as executor:
            executor.map(run, sosreports)

    def extract(self, sosreports, *, parallel=True, reextract=False):
        self._parallel(sosreports, 'extract', parallel=parallel, reextract=reextract)

    def sear(self, sosreports, *, parallel=True, resear=False):
        self._parallel(sosreports, 'sear', parallel=parallel, resear=resear)

    def create_json(self):
        return self.saucery.create_json()
