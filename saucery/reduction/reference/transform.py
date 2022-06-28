
from abc import abstractmethod
from functools import cached_property

from .reference import Reference


class TransformReference(Reference):
    '''TransformReference object.

    This base class should be used by any class that performs processing on
    another Reference, in a way that completely transforms the value, breaking
    the reference to our source's ReferencePathList content.

    Implementations should put all transformation work in transform(),
    using the passed ReferencePathList.

    This will create a new ReferencePath to store the transformed content.
    '''
    @abstractmethod
    def transform(self, pathlist):
        '''Transform the pathlist value.

        Subclasses must implement this. The return value should be bytes, or None.

        This will only be called once to get the value, which is then stored
        in our new ReferencePath file.

        The 'pathlist' parameter is a ReferencePathList, and will never be None,
        however the pathlist.value may be None.
        '''
        pass

    @cached_property
    def pathlist(self):
        source = self.reductions.reference(self.source)
        if source is None or source.pathlist is None:
            return None

        self.sos.analysis_files[self.name] = self.transform(source.pathlist)

        return [self.sos.analysis_files.path(self.name)]


class TransformValueReference(TransformReference):
    '''TransformValueReference object.

    This operates the same as TransformReference, except this implements transform()
    and subclasses should instead implement transform_value().
    '''
    def transform(self, pathlist):
        if pathlist.value is None:
            return None

        return self.transform_value(pathlist.value)

    @abstractmethod
    def transform_value(self, value):
        '''Transform the value.

        Subclasses must implement this. This works the same as transform() except
        the parameter is the value (in bytes) instead of the ReferencePathList.
        The 'value' parameter will never be None.

        This should return bytes, or None.
        '''
        pass
