
from datetime import datetime
from functools import cached_property

from ..definition import InvalidDefinitionError
from ..reference import ReferenceSourceDefinition

from .path import ReferencePathListResult


class InvalidAnalysisError(InvalidDefinitionError):
    pass


class Analysis(ReferenceSourceDefinition):
    '''Analysis class.

    This represents an analysis of reference(s).
    '''
    ERROR_CLASS = InvalidAnalysisError
    VALID_LEVELS = ('critical', 'error', 'warning', 'info', 'debug')

    @classmethod
    def TYPE(cls):
        return 'analysis'

    @classmethod
    def _add_fields(cls):
        return {
            'level': str,
            'description': str,
            'summary': str,
        }

    @classmethod
    def _field_defaults(cls):
        return {
            'level': 'info',
            'description': '',
            'summary': '',
        }

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
    def results(self):
        '''The results of our analysis.

        The default implementation here returns a new ReferencePathListResult object
        from our source pathlist.
        '''
        return ReferencePathListResult(self.source_pathlist)

    @property
    def conclusion(self):
        '''The conclusion for this analysis.'''
        return {
            'name': self.get('name'),
            'level': self.level,
            'summary': self.get('summary'),
            'description': self.get('description'),
            'normal': self.results.normal,
            'abnormal': self.results.abnormal,
            'unknown': self.results.unknown,
            'details': self.results.details,
        }
