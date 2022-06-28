
from abc import abstractmethod
from functools import cached_property

from .path import ReferencePathList
from .reference import Reference


class ParseReference(Reference):
    '''ParseReference object.

    This base class should be used by any class that performs processing on another Reference.

    The 'source' parameter must be a text string containing the name of a Reference.

    Implementations should put all processing work in parse() using the passed ReferencePathList,
    and returning a processed ReferencePathList.
    '''
    @abstractmethod
    def parse(self, pathlist):
        '''Parse the pathlist.

        Subclasses must implement this. The return value must be a ReferencePathList, or None.

        This will only be called once, and the returned list cached.

        The 'pathlist' parameter will never be None, however the pathlist.value may be None.
        '''
        pass

    @cached_property
    def pathlist(self):
        source = self.reductions.reference(self.source)
        if source is None or source.pathlist is None:
            return None

        return self.parse(source.pathlist)


class TransformReference(ParseReference):
    '''TransformReference object.

    This operates similarly to ParseReference, except subclasses should implement the transform()
    method, and return the transformed value as bytes, or None.

    This will create a new ReferencePath to store the transformed value.
    '''
    @abstractmethod
    def transform(self, value):
        '''Transform the value.

        Subclasses must implement this. The return value must be bytes, or None.

        This will only be called once, and the returned value cached.

        The 'value' parameter will never be None.
        '''
        pass

    def parse(self, pathlist):
        if pathlist.value is None:
            return None

        self.sos.analysis_files[self.name] = self.transform(source.pathlist.value)

        return ReferencePathList([self.sos.analysis_files.path(self.name)])
