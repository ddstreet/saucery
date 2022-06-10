
import re

from abc import abstractmethod
from collections import ChainMap
from datetime import datetime
from functools import cached_property
from itertools import chain

from ..definition import Definition
from ..definition import InvalidDefinitionError

from .compare import DictComparison
from .compare import NumberGeComparison
from .compare import NumberGtComparison
from .compare import NumberLeComparison
from .compare import NumberLtComparison
from .compare import StringEqComparison
from .conclusion import Conclusion


__all__ = [
    'InvalidAnalysisError',
    'Analysis',
]


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

    @property
    def name(self):
        return self.get('name')

    @cached_property
    def level(self):
        level = self.get('level').lower()
        if level not in self.VALID_LEVELS:
            self._raise(f"invalid level: '{level}'")
        return level

    @property
    def default_summary(self):
        return self.__class__.__name__

    @property
    def summary(self):
        return self.get('summary') or self.default_summary

    @property
    def default_description(self):
        return ''

    @property
    def description(self):
        return self.get('description') or self.default_description

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

    def source_dict(self, source=None):
        try:
            return self.source_reference(source).dict
        except AttributeError:
            self._raise(f"source reference is not DictReference: {source or self.source}")

    def source_value(self, source=None):
        ref = self.source_reference(source)
        if not ref:
            return None
        return ref.value


class BasicAnalysis(Analysis):
    @classmethod
    def TYPE(cls):
        return 'analysis'


class TextAnalysis(Analysis):
    def source_value(self, source=None):
        ref = self.source_reference(source)
        if not ref:
            return None
        return ref.value_text


class RegexAnalysis(TextAnalysis):
    @classmethod
    def TYPE(cls):
        return 'regex'

    @classmethod
    def fields(cls):
        return ChainMap({'regex': cls._field('text')},
                        super().fields())

    @cached_property
    def _results(self):
        if self.source_value() is None:
            return None
        return re.findall(self.get('regex'), self.source_value())


class ComparisonAnalysis(Analysis):
    '''ComparisonAnalysis object.

    This compares the source reference value to a specified value.

    This implementation has required keys:
      to: The value to compare to
    '''
    @classmethod
    def fields(cls):
        return ChainMap({'to': cls._field('text')},
                        super().fields())

    @property
    @abstractmethod
    def comparison_class(self):
        pass

    @property
    def comparison_a(self):
        return self.source_value()

    @property
    def comparison_b(self):
        return self.get('to')

    @property
    def comparison_args(self):
        return [self, self.comparison_a, self.comparison_b]

    @property
    def comparison_kwargs(self):
        return {}

    @cached_property
    def comparison(self):
        return self.comparison_class(*self.comparison_args, **self.comparison_kwargs)

    @property
    def _results(self):
        return [self.comparison.describe()]

    @property
    def _normal(self):
        return self.comparison.compare()


class IndirectComparisonAnalysis(ComparisonAnalysis):
    @property
    def comparison_b(self):
        return self.source_value(self.get('to'))


class TextComparisonAnalysis(ComparisonAnalysis, TextAnalysis):
    '''TextAnalysis object.

    Analysis of string value.

    This implementation has optional keys:
      strip: If the value should be stripped or not (boolean, default True)
      ignore_whitespace: If whitespace differences should be ignored (boolean, default True)

    Note 'ignore_whitespace' will only collapse each whitespace instance into a single space
    before comparison.
    '''
    @classmethod
    def fields(cls):
        return ChainMap({'strip': cls._field('boolean', default=True),
                         'ignore_whitespace': cls._field('boolean', default=True)},
                        super().fields())

    @property
    def comparison_kwargs(self):
        return ChainMap({'strip': self.get('strip'),
                         'ignore_whitespace': self.get('ignore_whitespace')},
                        super().comparison_kwargs)


class LtAnalysis(ComparisonAnalysis):
    @classmethod
    def TYPE(cls):
        return 'lt'

    @property
    def comparison_class(self):
        return NumberLtComparison


class LeAnalysis(ComparisonAnalysis):
    @classmethod
    def TYPE(cls):
        return 'le'

    @property
    def comparison_class(self):
        return NumberLeComparison


class EqAnalysis(TextComparisonAnalysis):
    @classmethod
    def TYPE(cls):
        return 'eq'

    @property
    def comparison_class(self):
        return StringEqComparison


class GeAnalysis(ComparisonAnalysis):
    @classmethod
    def TYPE(cls):
        return 'ge'

    @property
    def comparison_class(self):
        return NumberGeComparison


class GtAnalysis(ComparisonAnalysis):
    @classmethod
    def TYPE(cls):
        return 'gt'

    @property
    def comparison_class(self):
        return NumberGtComparison


class DictAnalysis(ComparisonAnalysis):
    '''DictAnalysis object.

    This compares two dictionaries.

    The 'source' reference must be a DictReference, and the 'to' value must be a dict.

    This implementation has required keys:
      fields: A list of *additional* key names to compare (default [])
      fields_from_source: If True, each key in the source DictReference is compared (default False)
      fields_from_to: If True, each key in the 'to' dict is compared (default True)
      ignore_fields: A list of key names to ignore (default [])
      ignore_missing: If True, keys not present in both dicts are ignored (default False)
      to: The dict to compare to
    '''
    @classmethod
    def fields(cls):
        return ChainMap({'fields': cls._field('list', default=[]),
                         'fields_from_source': cls._field('boolean', default=False),
                         'fields_from_to': cls._field('boolean', default=True),
                         'ignore_fields': cls._field('list', default=[]),
                         'ignore_missing': cls._field('boolean', default=False),
                         'to': cls._field('dict')},
                        super().fields())

    @cached_property
    def comparison(self):
        return DictComparison(*self.comparison_args, **self.comparison_kwargs)

    @property
    def comparison_a(self):
        return self.source_dict()

    @property
    def comparison_b(self):
        return self.get('to')

    @property
    def comparison_args(self):
        return super().comparison_args + [self.comparison_class]

    @property
    def comparison_kwargs(self):
        return ChainMap({'fields': self.get('fields'),
                         'fields_from_a': self.get('fields_from_source'),
                         'fields_from_b': self.get('fields_from_to'),
                         'ignore_fields': self.get('ignore_fields'),
                         'ignore_missing': self.get('ignore_missing')},
                        super().comparison_kwargs)

    @property
    def _results(self):
        return self.comparison.describe()


class DictLtAnalysis(DictAnalysis, LtAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictlt'


class DictLeAnalysis(DictAnalysis, LeAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictle'


class DictEqAnalysis(DictAnalysis, EqAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dicteq'


class DictGeAnalysis(DictAnalysis, GeAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictge'


class DictGtAnalysis(DictAnalysis, GtAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictgt'


class IndirectDictAnalysis(DictAnalysis):
    @classmethod
    def fields(cls):
        return ChainMap({'fields_from_source': cls._field('boolean', default=True),
                         'fields_from_to': cls._field('boolean', default=False),
                         'to': cls._field('text')},
                        super().fields())

    @property
    def comparison_b(self):
        return self.source_dict(self.get('to'))


class IndirectDictLtAnalysis(IndirectDictAnalysis, LtAnalysis):
    @classmethod
    def TYPE(cls):
        return 'indirectdictlt'


class IndirectDictLeAnalysis(IndirectDictAnalysis, LeAnalysis):
    @classmethod
    def TYPE(cls):
        return 'indirectdictle'


class IndirectDictEqAnalysis(IndirectDictAnalysis, EqAnalysis):
    @classmethod
    def TYPE(cls):
        return 'indirectdicteq'


class IndirectDictGeAnalysis(IndirectDictAnalysis, GeAnalysis):
    @classmethod
    def TYPE(cls):
        return 'indirectdictge'


class IndirectDictGtAnalysis(IndirectDictAnalysis, GtAnalysis):
    @classmethod
    def TYPE(cls):
        return 'indirectdictgt'


class DictFieldAnalysis(ComparisonAnalysis):
    '''DictFieldAnalysis object.

    This compares a field in the source DictReference to a provided value.

    The 'source' reference must be a DictReference.

    This implementation has required keys:
      field: The field to compare
      to: The value to compare to
    '''
    @classmethod
    def fields(cls):
        return ChainMap({'field': cls._field('text')},
                        super().fields())

    @property
    def comparison_a(self):
        return (self.source_dict() or {}).get(self.get('field'))


class DictFieldLtAnalysis(DictFieldAnalysis, LtAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictfieldlt'


class DictFieldLeAnalysis(DictFieldAnalysis, LeAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictfieldle'


class DictFieldEqAnalysis(DictFieldAnalysis, EqAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictfieldeq'


class DictFieldGtAnalysis(DictFieldAnalysis, GtAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictfieldgt'


class DictFieldGeAnalysis(DictFieldAnalysis, GeAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictfieldge'


class ForeachAnalysis(Analysis):
    '''ForeachAnalysis object.

    Perform analysis on a list of references.

    The 'source' reference value must be a list of reference names, one per line.

    This has required keys:
      as: The analysis definition to apply to each of the references
    '''
    @classmethod
    def TYPE(cls):
        return 'foreachanalysis'

    @classmethod
    def fields(cls):
        return ChainMap({'as': cls._field('dict')},
                        super().fields())

    @cached_property
    def analyses(self):
        v = self.source_value()
        if not v:
            return None

        definition = self.get('as')
        return [self.anonymous(ChainMap({'source': line}, definition))
                for line in v.splitlines()]

    @property
    def _results(self):
        if self.analyses is None:
            return None
        return list(chain(*[a.results for a in self.analyses]))

    @property
    def _normal(self):
        if self.analyses is None:
            return None
        normal = [a.normal for a in self.analyses]
        if None in normal:
            return None
        return all(normal)


class LogicalAnalysis(Analysis):
    @classmethod
    def fields(cls):
        return ChainMap({cls.TYPE(): cls._field('list')},
                        super().fields())

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
    '''AndAnalysis object.

    This requires all listed analysis definition to be normal.

    This has required fields:
      and: The analysis definitions
    '''
    @classmethod
    def TYPE(cls):
        return 'and'

    def is_normal(self, values):
        return all(values)


class OrAnalysis(LogicalAnalysis):
    '''OrAnalysis object.

    This requires any listed analysis definition to be normal.

    This has required fields:
      or: The analysis definitions
    '''
    @classmethod
    def TYPE(cls):
        return 'or'

    def is_normal(self, values):
        return any(values)


class DebugAnalysis(Analysis):
    '''DebugAnalysis object.

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


class TextDebugAnalysis(DebugAnalysis, TextAnalysis):
    @classmethod
    def TYPE(cls):
        return 'textdebug'


class DictDebugAnalysis(DebugAnalysis):
    @classmethod
    def TYPE(cls):
        return 'dictdebug'

    @property
    def _results(self):
        if self.source_dict() is None:
            return None
        return [self.source_dict()]


class IndirectDebugAnalysis(DebugAnalysis):
    @classmethod
    def TYPE(cls):
        return 'indirectdebug'

    def source_reference(self, source=None):
        return super().source_reference(source or self.source_value())
