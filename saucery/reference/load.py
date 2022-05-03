
import json
import yaml

from functools import cached_property
from functools import singledispatchmethod
from itertools import chain


class DefinitionLoader(object):
    def __init__(self, saucery, location, *, verbose=False):
        super().__init__()
        self.saucery = saucery
        self.location = location
        self.verbose = verbose

    @cached_property
    def definitions(self):
        return self._load_definitions(self.location)

    @singledispatchmethod
    def _definitions(self, definitions):
        raise InvalidDefinitionError(f'Unknown definition format: {definitions}')

    @_definitions.register
    def _definitions(self, definitions: list):
        return list(chain(*[self._definitions(d) for d in definitions]))

    @_definitions.register
    def _definitions(self, definitions: dict):
        try:
            return [Definition.create(definitions, self.saucery)]
        except InvalidDefinitionError as e:
            if self.verbose:
                print(str(e))
            raise

    def _load_file(self, path):
        filetype = path.suffix.lstrip('.').lower()
        if filetype == 'yaml':
            return yaml.safe_load(path.read_text())
        if filetype == 'json':
            return json.loads(path.read_text())
        if self.verbose:
            print(f"Ignoring unknown file type '{filetype}': {path}")
        return []

    def _load_definitions_from_file(self, path):
        try:
            return self._definitions(self._load_file(path))
        except InvalidDefinitionError as e:
            raise InvalidDefinitionError(f'Invalid definition {path}: {e}')

    def _load_definitions_from_dir(self, path):
        return chain(*[self._load_definitions(f)
                       for f in path.iterdir()])

    def _load_definitions(self, path):
        if path.is_file():
            return self._load_definitions_from_file(path)

        if path.is_dir() and not path.is_symlink():
            return self._load_definitions_from_dir(path)

        if self.verbose:
            print(f"Not loading definition '{path}'")
        return []
