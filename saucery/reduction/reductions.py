
import json
import logging
import yaml

from collections import ChainMap
from collections import UserDict
from contextlib import suppress
from pathlib import Path

from .analysis import Analysis
from .definition import InvalidDefinitionError
from .definition import Definition
from .reference import Reference


LOGGER = logging.Logger(__name__)


class Reductions(UserDict):
    def __init__(self, sos, location):
        super().__init__()
        self.sos = sos
        self._analyses = {}
        self._references = {}
        self.data = ChainMap(self._references, self._analyses)
        if not location:
            LOGGER.error('No location provided for Reductions')
        else:
            self._load(Path(location).expanduser().resolve())

    @property
    def analyses(self):
        return list(self._analyses.values())

    @property
    def references(self):
        return list(self._references.values())

    def __setitem__(self, key, value):
        if not value:
            raise ValueError('Delete key instead of setting value to None')

        if key in self:
            raise InvalidDefinitionError(f'Duplicate definition with name {key}')

        if isinstance(value, Reference):
            clsdict = self._references
        elif isinstance(value, Analysis):
            clsdict = self._analyses
        else:
            raise InvalidDefinitionError(f'Unknown definition class: {value.__class__}')
        clsdict[key] = value

    def __delitem__(self, key):
        for d in [self._references, self._analyses]:
            with suppress(KeyError):
                del d[key]
                return
        raise KeyError(key)

    def _load(self, location):
        for f in location.rglob('*.[jJ][sS][oO][nN]'):
            self._load_json(f)
        for f in location.rglob('*.[yY][aA][mM][lL]'):
            self._load_yaml(f)

    def _load_json(self, path):
        self._add_definitions(json.loads(path.read_text()))

    def _load_yaml(self, path):
        self._add_definitions(yaml.safe_load(path.read_text()))

    def _add_definitions(self, definitions):
        if isinstance(definitions, list):
            for d in definitions:
                self._add_definitions(d)
        elif isinstance(definitions, dict):
            Definition(definitions, self)
        else:
            raise InvalidDefinitionError(f'Unknown definition format: {definitions}')
