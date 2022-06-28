
from .reference import Reference


class ReduceReference(Reference):
    '''ReduceReference object.

    This base class should be used by any class that performs processing on
    another Reference, which only reduces the source Reference's value, but
    retains the ReferencePathList, or a reduced version of the list.

    The 'sourcereference' attribute should be used to access our source Reference,
    or None if our source Reference does not exist.

    The 'sourcelist' and 'sourcevalue' attributes can be used to access our source's
    referencelist and value attributes, respectively; if our source Reference does
    not exist, both attributes will be None.

    The 'source' must be the name of a Reference object.
    '''
    @property
    def sourcereference(self):
        return self.reductions.reference(self.source)

    def _sourceattr(self, attr):
        source = self.sourcereference
        if not source:
            return None
        return getattr(source, attr, None)

    @property
    def sourcelist(self):
        return self._sourceattr('pathlist')

    @property
    def sourcevalue(self):
        return self._sourceattr('value')
