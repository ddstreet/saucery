
import glob
import json
import yaml

from collections import ChainMap
from collections import UserDict
from functools import singledispatchmethod

from .analysis import Analysis
from .reference import Reference


class Reductions(UserDict):
    def __init__(self, sos, location, *, verbose=False):
        super().__init__()
        self.sos = sos
        self.location = Path(location).expanduser().resolve()
        self.verbose = verbose
        self._references = {}
        self._analyses = {}
        self.data = ChainMap(self._references, self._analyses)
        self._load()

    def __setitem__(self, key, value):
        if not value:
            raise ValueError(f'Delete key instead of setting value to None')

        if key in self:
            raise InvalidDefinitionError(f'Duplicate definition with name {key}')

        if isinstance(cls, Reference):
            clsdict = self._references
        elif isinstance(cls, Analysis):
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

    def _load(self):
        self._load_files(glob.iglob('**/*.[yY][aA][mM][lL]',
                                    root_dir=self.location, recursive=True))
        self._load_files(glob.iglob('**/*.[jJ][sS][oO][nN]',
                                    root_dir=self.location, recursive=True))

    def _load_files(self, files):
        for f in files:
            path = self.location / f
            if not str(path.resolve()).startswith(str(self.location)):
                continue
            self._load_definitions(path)

    def _load_definitions(self, path):
        filetype = path.suffix.lstrip('.').lower()
        if filetype == 'yaml':
            definitions = yaml.safe_load(path.read_text())
        elif filetype == 'json':
            definitions = json.loads(path.read_text())
        else:
            if self.verbose:
                print(f"Ignoring unknown file type '{filetype}': {path}")
            return
        self._add_definitions(definitions)

    def _add_definitions(self, definitions):
        if isinstance(definitions, list):
            for d in definitions:
                self._add_definitions(d)
        elif isinstance(definitions, dict):
            Definition(definitions, self.sos)
        else:
            raise InvalidDefinitionError(f'Unknown definition format: {definitions}')
