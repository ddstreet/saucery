
from collections import ChainMap
from datetime import datetime
from functools import cached_property

from ..definition import Definition
from ..definition import InvalidDefinitionError

from .conclusion import Conclusion


class InvalidAnalysisError(InvalidDefinitionError):
    pass


class Analysis(Definition):
    '''Analysis object.

    This represents an analysis of reference(s).
    '''
    ERROR_CLASS = InvalidAnalysisError
    VALID_LEVELS = ('critical', 'error', 'warning', 'info', 'debug')

    @classmethod
    def fields(cls):
        return ChainMap({'level': cls._field('text', default='info'),
                         'description': cls._field('text', default=''),
                         'summary': cls._field('text', default='')},
                        super().fields())

    def setup(self):
        super().setup()
        # verify level is valid
        self.level

    @cached_property
    def level(self):
        level = self.get('level').lower()
        if level not in self.VALID_LEVELS:
            self._raise(f"invalid level: '{level}'")
        return level

    @property
    def summary(self):
        return self.get('summary')

    @property
    def description(self):
        return self.get('description')

    @property
    def conclusion(self):
        return Conclusion(self)

    def _analyse(self):
        '''Perform the analysis.

        By default, this simply gets the results.
        '''
        self._results

    def analyse(self):
        self._duration

    @cached_property
    def _duration(self):
        start = datetime.now()
        self._analyse()
        end = datetime.now()
        return end - start

    @property
    def duration(self):
        self.analyse()
        return self._duration

    @property
    def _results(self):
        if self.source_value() is None:
            return None
        return self.source_value()

    @property
    def results(self):
        '''Analysis results description.

        Returns None if no analysis could be performed, otherwise returns a list
        of strings describing the results of the analysis.
        '''
        self.analyse()
        return self._results

    @property
    def _normal(self):
        if self._results is None:
            return None
        return not self._results

    @property
    def normal(self):
        '''If the analysis results are normal.

        Returns None if no analysis could be performed, otherwise returns True
        if the analysis results are 'normal', and False if the analysis results
        are not 'normal'.
        '''
        self.analyse()
        return self._normal

    def source_reference(self, source=None):
        return self._reductions.get(source or self.source)

    def source_value(self, source=None):
        ref = self.source_reference(source)
        if not ref:
            return None
        return ref.value


class BasicAnalysis(Analysis):
    @classmethod
    def TYPE(cls):
        return 'analysis'
