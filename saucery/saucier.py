#!/usr/bin/python

import os

from concurrent import futures
from functools import cached_property
from functools import partial
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

    def _parallel(self, sosreports, action, parallel=True):
        sosreports = self._sosreports(sosreports)

        if not parallel:
            for s in sosreports:
                action(s)
            return

        if parallel is True:
            parallel = len(os.sched_getaffinity(0))
        with futures.ThreadPoolExecutor(max_workers=int(parallel)) as executor:
            executor.map(action, sosreports)

    def _cook(self, sosreport, *, extract=False, sear=False, force=False):
        if extract:
            sosreport.extract(reextract=force)
        if sear:
            sosreport.sear(resear=force)

    def cook(self, sosreports, *, extract=False, sear=False, update_menu=False, force=False, parallel=True):
        self._parallel(sosreports,
                       partial(self._cook, extract=extract, sear=sear, force=force),
                       parallel=parallel)

        if update_menu:
            self.update_menu()

    def extract(self, sosreports, *, parallel=False, reextract=False):
        self.cook(sosreports, extract=True, force=reextract, parallel=parallel)

    def sear(self, sosreports, *, parallel=False, resear=False):
        self.cook(sosreports, sear=True, force=resear, parallel=parallel)

    def update_menu(self):
        return self.saucery.update_menu()
