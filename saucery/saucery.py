#!/usr/bin/python3

import json
import logging
import tempfile

from functools import cached_property
from pathlib import Path

from saucery.base import SauceryBase
from saucery.sos import SOS


LOGGER = logging.getLogger(__name__)


class Saucery(SauceryBase):
    DEFAULT_SAUCERY_DIR = '/saucery'

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
        return path

    @property
    def menu(self):
        return self.saucerydir / 'menu.json'

    @property
    def sosreports(self):
        return [self.sosreport(s)
                for s in self.sosdir.iterdir()
                if s.is_file() and SOS.FILENAME_REGEX.match(s.name)]

    def _sosreport_path(self, sosreport):
        if isinstance(sosreport, SOS):
            return sosreport.sosreport
        return self.sosdir / sosreport

    def sosreport(self, sosreport):
        path = self._sosreport_path(sosreport)
        if not str(path.resolve()).startswith(str(self.sosdir.resolve())):
            raise ValueError(f'Sosreports must be located under {self.sosdir}: '
                             f'invalid location {path}')

        if isinstance(sosreport, SOS):
            return sosreport
        return SOS(instance=self, sosreport=path)

    def update_menu(self):
        LOGGER.info(f'Creating JSON index {self.menu}')
        if self.dry_run:
            return

        with tempfile.TemporaryDirectory(dir=self.menu.parent) as tmpdir:
            tmpmenu = Path(tmpdir) / 'menu.tmp'
            tmpmenu.write_text(json.dumps([s.json for s in self.sosreports],
                                          indent=2, sort_keys=True))
            tmpmenu.rename(self.menu)
