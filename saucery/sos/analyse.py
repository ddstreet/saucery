
import logging
import magic
import os
import re
import shutil
import subprocess

from contextlib import suppress
from functools import cached_property


LOGGER = logging.getLogger(__name__)


class SOSAnalysisError(Exception):
    pass


class SOSAnalysis(object):
    def __init__(self, sos):
        self.sos = sos

    @property
    def name(self):
        return self.sos.name

    def analyse(self):
        '''Perform all analysis.

        This only performs case/customer detection if the attribute is not currently set
        for the sosreport, and only performs external analysis if external_analysis_keys
        is configured with key names.
        '''
        LOGGER.debug(f'Detecting newlines: {self.name}')
        self.detect_newlines()
        LOGGER.debug(f'Gathering conclusions: {self.name}')
        self.conclusions
        if not self.sos.case:
            LOGGER.debug(f'Detecting case: {self.name}')
            self.case
        if not self.sos.customer:
            LOGGER.debug(f'Detecting customer: {self.name}')
            self.customer
        if self.external_keys:
            LOGGER.debug(f'Performing external analysis: {self.name}')
            self.external

    def _get_conclusion(self, analysis):
        LOGGER.debug(f'Getting conclusion for {analysis.name}: {self.name}')
        with suppress(Exception):
            return dict(analysis.conclusion)
        LOGGER.exception(f'Analysis {analysis.name} failed, skipping')
        return None

    @cached_property
    def conclusions(self):
        return [c for c in map(self._get_conclusion, self.sos.reductions.analyses) if c]

    def detect_newlines(self):
        if self.sos.linesdir.exists() and not self.sos.dry_run:
            shutil.rmtree(self.sos.linesdir)

        for f in self.sos.files_json:
            if f.get('type') == 'file':
                self.create_newline_file(f.get('path'))
            elif f.get('type') == 'link':
                self.create_newline_symlink(f.get('path'))

    def create_newline_symlink(self, f):
        path = self.sos.file(f)
        lines_path = self.sos.linesdir / f
        lines_path.parent.mkdir(parents=True, exist_ok=True)
        lines_path.symlink_to(os.readlink(str(path)))

    def create_newline_file(self, f):
        path = self.sos.file(f)
        if not magic.from_file(str(path), mime=True).startswith('text'):
            return
        lines_path = self.sos.linesdir / f
        lines_path.parent.mkdir(parents=True, exist_ok=True)
        lines_path.write_text(','.join(map(str, self.newline_iter(path))))

    def newline_iter(self, path):
        return (newline.end() for newline in re.finditer(b'^|\n|(?<!\n)$', path.read_bytes()))

    @cached_property
    def case(self):
        case = self.get_case_from_config_lookup() or self.get_case_from_filename()
        if not case:
            LOGGER.debug(f'Could not detect case: {self.name}')
        return case

    def get_case_from_config_lookup(self):
        case = self.run_config_lookup('case')
        if case:
            LOGGER.info(f"Got case '{case}' based on configured lookup: {self.name}")
        return case

    def get_case_from_filename(self):
        case = self.sos._sosreport_match.group('case')
        if case:
            LOGGER.info(f"Got case '{case}' based on filename: {self.name}")
        return case

    @cached_property
    def customer(self):
        customer = self.get_customer_from_config_lookup()
        if not customer:
            LOGGER.debug(f'Could not detect customer: {self.name}')
        return customer

    def get_customer_from_config_lookup(self):
        customer = self.run_config_lookup('customer')
        if customer:
            LOGGER.info(f"Set 'customer' to '{customer}' based on configured lookup: {self.name}")
        return customer

    @cached_property
    def external_keys(self):
        return self.sos.config.get('external_analysis_keys', '').split()

    @cached_property
    def external(self):
        if not self.external_keys:
            LOGGER.debug(f'No external analysis keys defined: {self.name}')
            return {}
        return {k: self.run_config_lookup(k) for k in self.external_keys}

    def run_config_lookup(self, key):
        cmd = self.sos.config.get(f'lookup_{key}')
        if not cmd:
            LOGGER.debug(f"No config for '{key}', skipping: {self.name}")
            return None
        cmd = [c.format_map(vars(self.sos)) for c in cmd.split()]
        cmdstr = ' '.join(cmd)

        LOGGER.debug(f"Lookup for '{key}': {cmdstr}")
        try:
            result = subprocess.run(cmd, encoding='utf-8',
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.SubprocessException:
            LOGGER.exception(f"Error running '{cmdstr}': {self.name}")
            return None

        if result.returncode != 0:
            LOGGER.error(f"Error ({result.returncode}) running '{cmdstr}': {self.name}")
            if result.stderr.strip():
                LOGGER.error(result.stderr)
            return None

        LOGGER.debug(f"Looked up '{key}': {self.name}")
        return result.stdout
