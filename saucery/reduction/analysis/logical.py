
from abc import abstractmethod
from collections import ChainMap
from itertools import chain

from .analysis import Analysis


class LogicalAnalysis(Analysis):
    def setup(self):
        super().setup()
        self.analyses = [self.anonymous(ChainMap({'source': self.source}, definition))
                         for definition in self.get(self.TYPE())]

    @property
    def _results(self):
        if not self.analyses:
            return None
        return list(chain(*[a.results for a in self.analyses]))

    @property
    def _normal(self):
        if not self.analyses:
            return None
        normal = [a.normal for a in self.analyses]
        if None in normal:
            return None
        return self.is_normal(normal)

    @abstractmethod
    def is_normal(self, values):
        pass


class AndAnalysis(LogicalAnalysis):
    '''AndAnalysis class.

    This requires all listed analysis definition to be normal.

    This has required fields:
      and: The analysis definitions
    '''
    @classmethod
    def TYPE(cls):
        return 'and'

    @classmethod
    def _add_fields(cls):
        return {
            'and': list,
        }

    def is_normal(self, values):
        return all(values)


class OrAnalysis(LogicalAnalysis):
    '''OrAnalysis class.

    This requires any listed analysis definition to be normal.

    This has required fields:
      or: The analysis definitions
    '''
    @classmethod
    def TYPE(cls):
        return 'or'

    @classmethod
    def _add_fields(cls):
        return {
            'or': list,
        }

    def is_normal(self, values):
        return any(values)
