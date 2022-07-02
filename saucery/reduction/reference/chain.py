
from copy import deepcopy

from .reference import Reference


class ChainReference(Reference):
    '''ChainReference class.

    This creates a chain of references.

    This implementation has additional required keys:
      chain: The list of references in the chain

    Each entry in the chain list must be a reference definition, but
    without its 'name' or 'source' set; the first entry's 'source'
    will be set to our 'source', and each following entry's 'source'
    will be set to the previous entry's auto-created 'name'.
    '''
    @classmethod
    def TYPE(cls):
        return 'chain'

    @classmethod
    def _add_fields(cls):
        return {
            'chain': 'list',
        }

    def setup(self):
        super().setup()

        # Build the chain at setup time, to detect config errors
        self._chain = self._build_chain()

    def _build_chain(self):
        if len(self.get('chain')) == 0:
            self._raise('requires at least one chain entry')
        chain = []
        source = self.source
        for definition in deepcopy(self.get('chain')):
            for field in ['name', 'source']:
                if field in definition:
                    self._raise(f"entries must not include '{field}'")

            definition['source'] = source
            reference = self.anonymous(definition)
            chain.append(reference)
            source = reference.get('name')
        return chain

    @property
    def pathlist(self):
        return self._chain[-1].pathlist
