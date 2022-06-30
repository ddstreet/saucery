
from abc import abstractmethod
from collections import ChainMap
from functools import cached_property

from .analysis import Analysis
from .comparison import DictComparison
from .comparison import NumberGeComparison
from .comparison import NumberGtComparison
from .comparison import NumberLeComparison
from .comparison import NumberLtComparison
from .comparison import StringEqComparison


class ComparisonAnalysis(Analysis):
    '''ComparisonAnalysis class.

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


class TextComparisonAnalysis(ComparisonAnalysis):
    '''TextAnalysis class.

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
    '''DictAnalysis class.

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
    '''DictFieldAnalysis class.

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
