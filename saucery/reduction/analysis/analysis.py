
from abc import abstractmethod
from datetime import datetime
from functools import cached_property

from ..definition import Definition
from ..definition import InvalidDefinitionError

from .conclusion import Conclusion


class InvalidAnalysisError(InvalidDefinitionError):
    pass


class Analysis(Definition):
    '''Analysis class.

    This represents an analysis of reference(s).
    '''
    ERROR_CLASS = InvalidAnalysisError
    VALID_LEVELS = ('critical', 'error', 'warning', 'info', 'debug')

    @classmethod
    def _add_fields(cls):
        return {
            'level': str,
            'description': str,
            'summary': str,
        }

    @classmethod
    def _field_default(cls, field):
        return {
            'level': 'info',
            'description': '',
            'summary': '',
        }.get(field, super()._field_default(field))

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

    @property
    def duration(self):
        self.results
        return self._duration

    @property
    @abstractmethod
    def _results(self):
        pass

    @cached_property
    def results(self):
        '''Analysis results description.

        Returns None if no analysis could be performed, otherwise returns a list
        of strings describing the results of the analysis.

        Subclasses should not override this, but instead should implement _results
        so this class can generate the analysis duration.
        '''
        start = datetime.now()
        try:
            return self._results
        finally:
            self._duration = datetime.now() - start

    @property
    def normal(self):
        '''If the analysis results are normal.

        Returns None if no analysis could be performed, otherwise returns True
        if the analysis results are 'normal' (False), and False if the analysis
        results are not 'normal' (True).
        '''
        if self.results is None:
            return None
        return not self.results

    @property
    def source_reference(self):
        return self.reductions.reference(self.source)

    @property
    def source_value(self):
        ref = self.source_reference
        if ref is None:
            return None
        return ref.value


class BasicAnalysis(Analysis):
    @classmethod
    def TYPE(cls):
        return 'analysis'

    @property
    def _results(self):
        return self.source_value
