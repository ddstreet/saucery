#!/usr/bin/python3

import logging
import os

from collections import ChainMap
from contextlib import suppress
from functools import cached_property
from functools import lru_cache
from functools import singledispatchmethod
from pathlib import Path

from . import json
from .base import SauceryBase
from .sos import SOS


LOGGER = logging.getLogger(__name__)


class Saucery(SauceryBase):
    DEFAULT_SAUCERY_DIR = '/saucery'

    @property
    def environconfig(self):
        # Special case for simple 'SAUCERY' in env; use that for saucerydir
        return ChainMap(super().environconfig,
                        {k.lower(): v for k, v in os.environ.items()
                         if k == 'SAUCERY'})

    @property
    def defaultconfig(self):
        return {'saucery': self.DEFAULT_SAUCERY_DIR}

    @property
    def saucerydir(self):
        path = Path(self.config.get('saucery'))
        if not path.exists():
            raise ValueError(f'Saucery location does not exist, please create it: {path}')
        if not path.is_dir():
            raise ValueError(f'Saucery location is not a dir, please fix: {path}')
        return path

    @cached_property
    def sosdir(self):
        path = self.saucerydir / 'sos'
        if not path.is_dir():
            if not self.dry_run:
                path.mkdir()
        return path.resolve()

    @property
    def menu(self):
        return self.saucerydir / 'menu.json'

    @cached_property
    def _sosreports(self):
        self._sosdir_mtime = self.sosdir.stat().st_mtime
        return sorted([self.sosreport(s)
                       for s in self.sosdir.iterdir()
                       if s.is_file() and SOS.valid_filename(s.name)],
                      key=lambda s: s.name)

    @property
    def sosreports(self):
        if getattr(self, '_sosdir_mtime', None) != self.sosdir.stat().st_mtime:
            with suppress(AttributeError):
                del self._sosreports
        return self._sosreports

    def sosreport_index(self, sosreport):
        sosreports = self.sosreports
        if sosreport in sosreports:
            return sosreports.index(sosreport)
        return None

    @singledispatchmethod
    def sosreport(self, sosreport):
        raise ValueError(f"Can't lookup sosreport from type '{type(sosreport)}'")

    @sosreport.register
    def _(self, sosreport: SOS):
        return sosreport

    @sosreport.register
    def _(self, sosreport: str):
        try:
            index = int(sosreport)
        except ValueError:
            pass
        else:
            return self.sosreport(index)
        return self.sosreport(Path(sosreport))

    @sosreport.register
    def _(self, sosreport: int):
        try:
            return self.sosreports[sosreport]
        except IndexError:
            raise ValueError(f'No sosreport found for index {sosreport}')

    @sosreport.register
    def _(self, sosreport: Path):
        path = str(self.sosdir.joinpath(sosreport).resolve())
        if not path.startswith(str(self.sosdir)):
            raise ValueError(f'Sosreports must be located under {self.sosdir}: '
                             f'invalid location {path}')

        return self._sos(path)

    @lru_cache(maxsize=None)
    def _sos(self, path):
        return SOS(instance=self, sosreport=path)

    def update_menu(self):
        LOGGER.info(f'Creating JSON index {self.menu}')
        if self.dry_run:
            return

        entries = [s.json for s in self.sosreports if s.extracted or s.mounted]
        menu = json.dumps(entries, indent=2, sort_keys=True)
        self.menu.write_text(menu)
