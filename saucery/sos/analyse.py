
import logging
import subprocess

from collections.abc import Mapping
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
        if not self.sos.case:
            LOGGER.debug(f'Detecting case: {self.name}')
            self.case
        if not self.sos.customer:
            LOGGER.debug(f'Detecting customer: {self.name}')
            self.customer
        # Note - need to perform external analysis *first*, as our built-in analysis
        # might reference the external results
        if self.external_keys:
            LOGGER.debug(f'Performing external analysis: {self.name}')
            self.external
        LOGGER.debug(f'Gathering conclusions: {self.name}')
        self.conclusions

    def _get_conclusion(self, analysis):
        LOGGER.debug(f'Getting conclusion for {analysis.name}: {self.name}')
        with suppress(Exception):
            return dict(analysis.conclusion)
        LOGGER.exception(f'Analysis {analysis.name} failed, skipping')
        return None

    @cached_property
    def conclusions(self):
        return [c for c in map(self._get_conclusion, self.sos.reductions.analyses) if c]

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
        cmd = [c.format_map(SOSMapping(self.sos)) for c in cmd.split()]
        cmdstr = ' '.join(cmd)

        LOGGER.debug(f"Running '{key}' command: {cmdstr}")
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

        LOGGER.debug(f"Finished command for '{key}': {self.name}")
        return result.stdout


class SOSMapping(Mapping):
    def __init__(self, sos):
        self.sos = sos

    def __getitem__(self, key):
        with suppress(AttributeError):
            return getattr(self.sos, key)
        raise KeyError(key)

    def __iter__(self):
        return (a for a in dir(self.sos) if not a.startswith('_'))

    def __len__(self):
        return len(list(self))
