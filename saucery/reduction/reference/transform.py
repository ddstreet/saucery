
from collections.abc import abstractmethod

from .reduce import ReduceReference


class TransformReference(ReduceReference):
    '''TransformReference object.

    This base class should be used by any class that performs processing on
    another Reference, in a way that completely transforms the value, breaking
    the reference to our source's ReferencePathList content.

    Implementations should put all transformation work in the getter for the
    'transformed_value' attribute. No transformation work should happen until
    this attribute is accessed.

    This will create a new ReferencePath to store the transformed content.
    '''
    @property
    @abstractmethod
    def transformed_value(self):
        '''The transformed value.

        Subclasses must implement this. The return value should be bytes, or None.

        This will only be called once to get the value, which is then stored
        in our new ReferencePath file.
        '''
        pass

    @cached_property
    def _transformed_referencepath(self):
        self.sos.analysis_files[self.name] = self.transformed_value
        return self.sos.analysis_files.path(self.name)

    @property
    def _sourcepaths(self):
        return [self._transformed_referencepath]

