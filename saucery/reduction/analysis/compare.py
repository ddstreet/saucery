
import json
import operator
import re
import yaml

from abc import ABC
from abc import abstractmethod
from contextlib import suppress
from functools import cached_property
from functools import lru_cache

from saucery.reduction.definition import InvalidDefinitionError


class InvalidComparisonError(InvalidDefinitionError):
    pass


class Comparison(ABC):
    @staticmethod
    def __new__(cls, analysis, a, b, *args, **kwargs):
        if (a is None or b is None) and cls is not NoneComparison:
            return NoneComparison(analysis, a, b)
        return super().__new__(cls)

    def __init__(self, analysis, a, b, *args, **kwargs):
        super().__init__()
        self.analysis = analysis
        self.a = a
        self.b = b

    @classmethod
    def to_str(cls, value, *, strip=True, ignore_whitespace=False, **kwargs):
        if value is None:
            return None
        v = str(value)
        if strip:
            v = str.strip(v)
        if ignore_whitespace:
            v = re.sub(r'\s+', ' ', v)
        return v

    @classmethod
    def to_int(cls, value):
        with suppress((TypeError, ValueError)):
            return int(value)
        return None

    @abstractmethod
    def compare(self):
        pass

    @abstractmethod
    def describe(self):
        pass


class NoneComparison(Comparison):
    def compare(self):
        return None

    def describe(self):
        return f'{self.a} ? {self.b}'


class OpComparison(Comparison):
    @property
    @abstractmethod
    def operator(self):
        pass

    @property
    @abstractmethod
    def opstrings(self):
        pass

    @lru_cache
    def compare(self):
        return self.operator(self.a, self.b)

    @lru_cache
    def describe(self):
        ops = self.opstrings
        op = ops[0] if self.compare() else ops[1]
        return f'{self.a} {op} {self.b}'


class EqComparison(OpComparison):
    @property
    def operator(self):
        return operator.eq

    @property
    def opstrings(self):
        return ['==', '!=']


class LtComparison(OpComparison):
    @property
    def operator(self):
        return operator.lt

    @property
    def opstrings(self):
        return ['<', '>=']


class LeComparison(OpComparison):
    @property
    def operator(self):
        return operator.le

    @property
    def opstrings(self):
        return ['<=', '>']


class GeComparison(OpComparison):
    @property
    def operator(self):
        return operator.ge

    @property
    def opstrings(self):
        return ['>=', '<']


class GtComparison(OpComparison):
    @property
    def operator(self):
        return operator.gt

    @property
    def opstrings(self):
        return ['>', '<=']


class StringComparison(Comparison):
    def __init__(self, analysis, a, b, *args, **kwargs):
        super().__init__(analysis, self.to_str(a, **kwargs), self.to_str(b, **kwargs), *args, **kwargs)


class NumberComparison(Comparison):
    @staticmethod
    def __new__(cls, analysis, a, b, *args, **kwargs):
        return super().__new__(cls, analysis, cls.to_int(a), cls.to_int(b), *args, **kwargs)

    def __init__(self, analysis, a, b, *args, **kwargs):
        super().__init__(analysis, self.to_int(a), self.to_int(b), *args, **kwargs)


class StringEqComparison(StringComparison, EqComparison):
    pass


class NumberEqComparison(NumberComparison, EqComparison):
    pass


class NumberLtComparison(NumberComparison, LtComparison):
    pass


class NumberLeComparison(NumberComparison, LeComparison):
    pass


class NumberGeComparison(NumberComparison, GeComparison):
    pass


class NumberGtComparison(NumberComparison, GtComparison):
    pass


class DictComparison(Comparison):
    def __init__(self, analysis, a, b, compareclass, *args,
                 fields=None, fields_from_a=True, fields_from_b=True,
                 ignore_fields=None, ignore_missing=False,
                 **kwargs):
        for v in [a, b]:
            if not isinstance(v, dict):
                raise InvalidComparisonError(f'DictComparison parameter not dict: {v}')
        super().__init__(analysis, a, b)
        self.compareclass = compareclass
        self._fields = set(fields or [])
        self.fields_from_a = fields_from_a
        self.fields_from_b = fields_from_b
        self.ignore_fields = set(ignore_fields or [])
        self.ignore_missing = ignore_missing
        self.args = args
        self.kwargs = kwargs

    @lru_cache(maxsize=4096)
    def field_comparison(self, field):
        return self.compareclass(self.analysis, self.a.get(field), self.b.get(field),
                                 *self.args, **self.kwargs)

    def compare_field(self, field):
        return self.field_comparison(field).compare()

    def describe_field(self, field):
        return self.field_comparison(field).describe()

    @cached_property
    def fields(self):
        fields = self._fields
        if self.fields_from_a:
            fields |= set(self.a.keys())
        if self.fields_from_b:
            fields |= set(self.b.keys())
        return fields - self.ignore_fields

    @property
    def failed_fields(self):
        return [f for f in self.fields if self.compare_field(f) is False]

    @property
    def missing_fields(self):
        return [f for f in self.fields if self.compare_field(f) is None]

    @lru_cache
    def compare(self):
        if len(self.missing_fields) > 0 and not self.ignore_missing:
            return False
        return len(self.failed_fields) == 0

    @lru_cache
    def describe(self):
        if self.compare():
            return ''
        fields = self.failed_fields
        if not self.ignore_missing:
            fields += self.missing_fields
        return {f: self.describe_field(f) for f in fields}
