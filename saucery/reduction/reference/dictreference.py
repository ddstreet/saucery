
import json
import re

from abc import abstractmethod
from collections import ChainMap
from contextlib import suppress
from functools import cached_property

from .reference import FileReference
from .reference import Reference
from .reference import SubdirFileReference
from .textreference import TextReference
from .transform import IndirectReference


class DictReference(Reference):
    @property
    @abstractmethod
    def dict(self):
        pass

    @property
    def value(self):
        d = self.dict
        if d is None:
            return None
        return str(d)


class JsonDictReference(DictReference, TextReference):
    @classmethod
    def TYPE(cls):
        return 'jsondict'

    @cached_property
    def dict(self):
        v = self.source_text()
        if v is None:
            return None
        return json.loads(v)


class FileDictReference(DictReference, FileReference, TextReference):
    @classmethod
    def TYPE(cls):
        return 'filedict'

    def _k(self, path):
        return path.name

    def _v(self, path):
        return self._value_text(self.path_read(path))

    @property
    def dict(self):
        return {self._k(p): self._v(p) for p in self.paths if p.is_file()}


class SubdirFileDictReference(SubdirFileReference, FileDictReference):
    @classmethod
    def TYPE(cls):
        return 'subdirfiledict'


class IndirectDictReference(DictReference, TextReference):
    '''IndirectDictReference object.

    This converts each line of the source into a dictionary key: value pair.

    Any line that does not contain the separator is treated as a key with None value.
    Blank lines (or whitespace only lines) are ignored. If 'removecomments' is True,
    any line starting with the value in 'comment' is ignored.

    The value is the actual dict.

    This implementation has optional keys:
      strip: if leading and trailing whitespace should be stripped from the value (default True)
      separator: separator character (or string) to use (default '=')
      removecomments: if comment lines should be removed (default True)
      comment: what the character or string starting a comment is (default '#')

    Note the 'strip' key only applies to the value; each key is always stripped.
    '''
    @classmethod
    def TYPE(cls):
        return 'indirectdict'

    @classmethod
    def fields(cls):
        return ChainMap({'separator': cls._field('text', default='='),
                         'strip': cls._field('boolean', default=True),
                         'removecomments': cls._field('boolean', default=True),
                         'comment': cls._field('text', default=r'\s*#')},
                        super().fields())

    def _strip(self, value, force=False):
        if value and (self.get('strip') or force):
            return value.strip()
        return value

    def _line(self, line):
        if self.get('removecomments') and re.match(self.get('comment'), line):
            return None, None
        i = iter(re.split(self.get('separator'), line, maxsplit=1))
        return self._strip(next(i, None), True), self._strip(next(i, None))

    @cached_property
    def dict(self):
        with suppress(AttributeError):
            return self.source_reference().dict

        v = self.source_text()
        if v is None:
            return None
        lines = v.splitlines()
        return {k: v for k, v in map(self._line, lines) if k}


class DictFieldReference(IndirectReference):
    '''DictFieldReference object.

    This returns the value of a specific field in a DictReference.

    The 'source' must be a DictReference.

    This has additional required keys:
      field: The field name to lookup in the dict.

    Returns the value of the field, or None if the field could not be
    looked up for any reason.
    '''
    @classmethod
    def TYPE(cls):
        return 'dictfield'

    @classmethod
    def fields(cls):
        return ChainMap({'field': cls._field('text')},
                        super().fields())

    @cached_property
    def value(self):
        try:
            return (self.source_reference().dict or {}).get(self.get('field'))
        except AttributeError:
            return None
