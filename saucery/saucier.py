#!/usr/bin/python

import os

from concurrent import futures
from functools import cached_property
from pathlib import Path

from saucery.base import SauceryBase
from saucery.sos import SOS
from saucery.grocery import Grocery


class Saucier(SauceryBase):
    DEFAULTS = {
        'max_age': '1 day',
    }

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
        return self.saucery.sosreports

    def buy(self, item):
        sos = self.sosreport(item)
        self.grocery.buy(item, sos)
        sos.meta_key = item
        return sos

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

    def update_menu(self):
        return self.saucery.update_menu()
