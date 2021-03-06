
from abc import abstractmethod

from ..definition import Definition
from ..definition import InvalidDefinitionError
from ..definition import DefinitionSourceDefinition


class InvalidReferenceError(InvalidDefinitionError):
    pass


class Reference(Definition):
    '''Reference class.

    This represents a reference to content from the SOS.
    '''
    ERROR_CLASS = InvalidReferenceError

    @property
    @abstractmethod
    def pathlist(self):
        '''The source for this reference.

        Returns a ReferencePathList of ReferencePath objects.

        The objects cover the entire range of this reference's value.
        '''
        pass

    @property
    def value(self):
        '''The entire value of this reference.

        Returns bytes.
        '''
        return self.pathlist.value


class ReferenceSourceDefinition(DefinitionSourceDefinition):
    '''ReferenceSourceDefinition class.

    This represents a definition, where the 'source' is a Reference.
    '''
    @property
    def source_class(self):
        return Reference

    @property
    def source_pathlist(self):
        '''The source.pathlist.

        Returns None if our source is None, otherwise returns source.pathlist.
        '''
        return self.source.pathlist if self.source else None

    @property
    def source_value(self):
        '''The source.value.

        Returns None if our source is None, otherwise returns source.value.
        '''
        return self.source.value if self.source else None


class ReferenceSourceReference(Reference, ReferenceSourceDefinition):
    '''ReferenceSourceReference class.

    This represents a reference, where the 'source' is a Reference.
    '''
    pass
