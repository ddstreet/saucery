
from collections import ChainMap
from copy import copy
from functools import cached_property

from .reference import CommandReference
from .reference import Reference
from .reference import FileReference


class IndirectReference(Reference):
    '''IndirectReference object.

    This represents a reference to another Reference object.

    The 'source' must refer to another Reference object name.

    Note that this is unlikely to be useful when used directly;
    this is mainly useful as a base class for other reference classes.
    '''
    @classmethod
    def TYPE(cls):
        return 'indirect'

    @classmethod
    def fields(cls):
        return ChainMap({'source': cls._field(['text', 'dict'])},
                        super().fields())

    def source_reference(self, source=None):
        return self.references.get(source or self.source)

    def _source_attr(self, attr, source=None):
        return getattr(self.source_reference(source), attr, None)

    def source_value(self, source=None):
        return self._source_attr('value', source)

    def source_bytes(self, source=None):
        return self._source_attr('value_bytes', source)

    def source_text(self, source=None):
        return self._source_attr('value_text', source)

    @property
    def value(self):
        return self.source_value()


class IndirectFileReference(IndirectReference, FileReference):
    '''IndirectFileReference object.

    This creates a FileReference using the value from another reference.

    Instead of using the 'source' field as the filename, the indirect
    reference's value is used as the filename. The indirect reference
    value must be one (or more) lines, with only the filename (or file glob)
    on each line.

    Leading and trailing whitespace will be stripped, and empty lines removed.
    '''
    @classmethod
    def TYPE(cls):
        return 'indirectfile'

    @property
    def sources(self):
        v = self.source_text()
        if not v:
            return []
        return [f for f in map(str.strip, v.splitlines()) if f]


class IndirectCommandReference(IndirectFileReference, CommandReference):
    '''IndirectCommandReference object.

    This creates a CommandReference using the value from another reference.

    Instead of using the 'source' field as the filename, the indirect
    reference's value is used as the filename. The indirect reference
    value must be one (or more) lines, with only the filename (or file glob)
    on each line.

    Leading and trailing whitespace will be stripped, and empty lines removed.
    '''
    @classmethod
    def TYPE(cls):
        return 'indirectcommand'


class ChainReference(IndirectReference):
    '''ChainReference object.

    This creates a chain of references, and stores the value produced
    by the last reference in the chain.

    This implementation has additional required keys:
      chain: The list of references in the chain

    Each entry in the chain list must be a reference definition, but
    without its 'name' or 'source' set; the first entry's 'source'
    will be set to our 'source', and each following entry's 'source'
    will be set to the previous entry's auto-created 'name'.

    Note that a 'file' type (or subclass) reference cannot be used in the
    chain; only 'indirect' type (or subclass) references can be used.
    Instead of using 'file' or 'command' references in the chain, use
    'indirectfile' or 'indirectcommand' references.
    '''
    @classmethod
    def TYPE(cls):
        return 'chain'

    @classmethod
    def fields(cls):
        return ChainMap({'chain': cls._field('list')}, 
                        super().fields())

    def setup(self):
        super().setup()
        self._chain = self._build_chain()

    def _build_chain(self):
        if len(self.get('chain')) == 0:
            self._raise(f'requires at least one chain entry')
        reference = None
        chain = []
        source = self.source
        for definition in map(copy, self.get('chain')):
            for field in ['name', 'source']:
                if field in definition:
                    self._raise(f"entries must not include '{field}'")
            if definition.get('type') == 'file':
                definition['type'] = 'indirectfile'
            if definition.get('type') == 'command':
                definition['type'] = 'indirectcommand'

            definition['source'] = source
            reference = self.anonymous(definition, references=reference)
            chain.append(reference)
            source = reference.get('name')
        return chain

    @property
    def value(self):
        return self._chain[-1].value


class ForeachReference(IndirectReference):
    @classmethod
    def TYPE(cls):
        return 'foreach'

    @classmethod
    def fields(cls):
        return ChainMap({'as': cls._field('dict'),
                         'field': cls._field('text', default='source')},
                        super().fields())

    def anonymous_references(self):
        return [self.anonymous(ChainMap({self.get('field'): l}, self.get('as')), private=False)
                for l in (super().value or '').splitlines() if l]

    @cached_property
    def value(self):
        return '\n'.join([r.get('name') for r in self.anonymous_references()]) or None
