
from collections import ChainMap

from .analysis import Analysis


class DebugAnalysis(Analysis):
    '''DebugAnalysis class.

    This creates an informational/debug conclusion.

    The conclusion 'description' will default to the name of the 'source',
    and the 'results' will be the source 'value'.

    The level defaults to 'debug'.

    The 'normal' property will be None if the source value is None,
    otherwise it will be True.
    '''
    @classmethod
    def TYPE(cls):
        return 'debug'

    @classmethod
    def fields(cls):
        return ChainMap({'level': cls._field('text', default='debug')},
                        super().fields())

    @property
    def default_description(self):
        return self.source

    @property
    def _results(self):
        if self.source_value() is None:
            return None
        return [self.source_value()]

    @property
    def _normal(self):
        return None if self._results is None else True
