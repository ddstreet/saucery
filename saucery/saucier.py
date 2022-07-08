#!/usr/bin/python

import logging
import os

from concurrent import futures
from functools import partial
from pathlib import Path

from . import json
from .base import SauceryBase
from .sos import SOS


LOGGER = logging.getLogger(__name__)


class Saucier(SauceryBase):
    def sosreport(self, name):
        if isinstance(name, str) and not SOS.valid_filename(name):
            # See if we match an existing sosreport name (without the suffix)
            basename = Path(name).name
            for s in self.saucery.sosreports:
                if basename == s.name:
                    return s
        return self.saucery.sosreport(name)

    def _sosreports(self, sosreports=None, state=None):
        state = state or []
        for s in sosreports or self.saucery.sosreports:
            if state and set(state).isdisjoint(set(s.state)):
                continue
            try:
                yield self.sosreport(s)
            except ValueError as e:
                LOGGER.info(e)

    def sosreports(self, sosreports=None, state=None):
        return list(self._sosreports(sosreports, state=state))

    def print_sosreports(self, sosreports):
        for sos in self._sosreports(sosreports):
            if LOGGER.isEnabledFor(logging.DEBUG):
                index = f'{self.saucery.sosreport_index(sos)}: '
                state = ','.join(sos.state)
                if state:
                    state = f' ({state})'
                LOGGER.info(f'{index}{sos}{state}')
            else:
                LOGGER.info(str(sos))

    def print_analysis(self, sosreports):
        for sos in self._sosreports(sosreports):
            if sos.analysed:
                LOGGER.debug(f'{sos}:')
                LOGGER.info(json.dumps(sos.conclusions, indent=2))
            else:
                LOGGER.info(f'Not analysed: {sos}')

    def _parallel(self, sosreports, action, parallel=True):
        sosreports = self.sosreports(sosreports)

        if not parallel:
            for s in sosreports:
                action(s)
            return

        if parallel is True:
            parallel = len(os.sched_getaffinity(0))

        LOGGER.info(f'Starting processing {len(sosreports)} sosreports...')
        with futures.ThreadPoolExecutor(max_workers=int(parallel)) as executor:
            submissions = {executor.submit(action, s): s for s in sosreports}
            while any(map(lambda future: future.running(), submissions)):
                (_, not_done) = futures.wait(submissions, timeout=60)
                for (index, future) in enumerate(not_done):
                    sos = submissions.get(future)
                    LOGGER.info(f'Still processing [{index+1}/{len(not_done)}]: {sos.name}')
            for future in submissions:
                e = future.exception()
                if e:
                    sos = submissions.get(future)
                    LOGGER.error(f'Error processing {sos}: {e}')
                    if LOGGER.isEnabledFor(logging.DEBUG):
                        LOGGER.exception(e)
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
        for s in self._sosreports(sosreports):
            s.unmount()

    def analyse(self, sosreports, *, parallel=False, reanalyse=False):
        self.process(sosreports, analyse=True, force=reanalyse, parallel=parallel)

    def update_menu(self):
        return self.saucery.update_menu()
