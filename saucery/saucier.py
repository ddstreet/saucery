#!/usr/bin/python

import logging
import os

from concurrent import futures
from functools import partial
from pathlib import Path

from .base import SauceryBase
from .sos import SOS


LOGGER = logging.getLogger(__name__)


class Saucier(SauceryBase):
    def sosreport(self, name):
        if isinstance(name, SOS):
            return name
        return self.saucery.sosreport(Path(name).name)

    @property
    def sosreports(self):
        return self.saucery.sosreports

    def _sosreports(self, sosreports):
        soses = []
        for s in sosreports:
            try:
                soses.append(self.sosreport(s))
            except ValueError as e:
                LOGGER.info(e)
        return soses

    def print_sosreports(self, sosreports):
        if not sosreports:
            sosreports = self.sosreports
        for sos in map(self.sosreport, sosreports):
            if LOGGER.isEnabledFor(logging.DEBUG):
                states = ['invalid', 'extracted', 'squashed', 'mounted', 'analysed']
                state = ','.join([s for s in states if getattr(sos, s, False)])
            else:
                state = ''
            if state:
                state = f' ({state})'
            LOGGER.info(f'{sos}{state}')

    def _parallel(self, sosreports, action, parallel=True):
        sosreports = self._sosreports(sosreports)

        if not parallel:
            for s in sosreports:
                action(s)
            return

        if parallel is True:
            parallel = len(os.sched_getaffinity(0))

        LOGGER.info(f'Starting processing {len(sosreports)} sosreports...')
        with futures.ThreadPoolExecutor(max_workers=int(parallel)) as executor:
            submissions = {executor.submit(action, s): s for s in sosreports}
            while any(map(lambda f: f.running(), submissions)):
                (_, not_done) = futures.wait(submissions, timeout=60)
                for (i, r) in enumerate(not_done):
                    sos = submissions.get(r)
                    LOGGER.info(f'Still processing [{i}/{len(not_done)}]: {sos.name}')
        LOGGER.info(f'Finished processing {len(sosreports)} sosreports')

    def _process(self, sosreport, *,
                 extract=False, squash=False, mount=False, analyse=False,
                 force=False):
        if extract:
            sosreport.extract(reextract=force)
        if squash:
            sosreport.squash(resquash=force)
        if mount:
            sosreport.mount(remount=force)
        if analyse:
            sosreport.analyse(reanalyse=force)

    def process(self, sosreports, *,
                extract=False, squash=False, mount=False, analyse=False,
                update_menu=False, force=False, parallel=True):
        self._parallel(sosreports,
                       partial(self._process,
                               extract=extract, squash=squash, mount=mount, analyse=analyse,
                               force=force),
                       parallel=parallel)

        if update_menu:
            self.update_menu()

    def extract(self, sosreports, *, parallel=False, reextract=False):
        self.process(sosreports, extract=True, force=reextract, parallel=parallel)

    def squash(self, sosreports, *, parallel=False, resquash=False):
        self.process(sosreports, squash=True, force=resquash, parallel=parallel)

    def mount(self, sosreports, *, parallel=False, remount=False):
        self.process(sosreports, mount=True, force=remount, parallel=parallel)

    def unmount(self, sosreports):
        for s in map(self.sosreport, sosreports):
            s.unmount()

    def analyse(self, sosreports, *, parallel=False, reanalyse=False):
        self.process(sosreports, analyse=True, force=reanalyse, parallel=parallel)

    def update_menu(self):
        return self.saucery.update_menu()
