
from abc import abstractmethod

from ..definition import Definition
from ..definition import InvalidDefinitionError


class InvalidReferenceError(InvalidDefinitionError):
    pass


class Reference(Definition):
    '''Reference object.

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

        Returns a bytes object.
        '''
        return self.sourcelist.value

    @property
    def size(self):
        '''The size of this reference value.'''
        return self.sourcelist.length
