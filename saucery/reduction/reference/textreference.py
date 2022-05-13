
import re

from collections import ChainMap
from functools import cached_property
from itertools import chain

from .reference import FileReference
from .transform import IndirectReference


class TextReference(IndirectReference):
    '''TextReference object.

    This decodes the source Reference value from bytes to str.

    This implementation has optional keys:
      encoding: The encoding to use (default 'utf-8')
      errors: The error handling to use (default 'backslashreplace')

    If the source Reference value is already a string, this passes it
    along unmodified.
    '''
    @classmethod
    def TYPE(cls):
        return 'text'

    @classmethod
    def fields(cls):
        return ChainMap({'encoding': cls._field('text', default='utf-8'),
                         'errors': cls._field('text', default='backslashreplace')},
                        super().fields())

    @property
    def _value_conversion_kwargs(self):
        return {'encoding': self.get('encoding'), 'errors': self.get('errors')}

    @property
    def value(self):
        return self._value_text(super().value, **self._value_conversion_kwargs)


class LsReference(FileReference):
    '''LsReference object.

    This lists file(s) and dir(s), similar to the 'ls' command.

    This has optional keys:
      directory: Like ls -d, if True list dirs themselves, not contents (default False)
      listfiles: If True, entries that are files are included (default True)
      listdirs: If True, entries that are dirs are included (default False)
      listlinks: If True, entries that are symlinks are included (default False)
      absolute: If True, each entry will include the full path (default False)
    '''
    @classmethod
    def TYPE(cls):
        return 'ls'

    @classmethod
    def fields(cls):
        return ChainMap({'directory': cls._field('boolean', default=False),
                         'listfiles': cls._field('boolean', default=True),
                         'listdirs': cls._field('boolean', default=False),
                         'listlinks': cls._field('boolean', default=False),
                         'absolute': cls._field('boolean', default=False)},
                        super().fields())

    def _name(self, entry):
        if self.get('absolute'):
            return self._relative_sospath(entry)
        return entry.name

    def _filter(self, entry):
        if entry.is_symlink():
            return self.get('listlinks')
        if entry.is_dir():
            return self.get('listdirs')
        if entry.is_file():
            return self.get('listfiles')
        return False

    def _expanddir(self, entry):
        if entry.is_dir() and not self.get('directory'):
            return entry.iterdir()
        return [entry]

    @cached_property
    def paths(self):
        return filter(self._filter, chain.from_iterable(map(self._expanddir, super().paths)))

    @cached_property
    def value(self):
        return '\n'.join(map(self._name, self.paths)) or None


class SplitReference(TextReference):
    '''SplitReference object.

    This applies python regex 'split' function. The resulting value contains
    the split strings, one on each line.

    This implementation has optional keys:
      pattern: The regex pattern to apply
      max: The maximum number of splits (default no max)
      splitlines: If true, the pattern is applied to each line (default true)

    If 'splitlines' is false, the pattern is applied once to the entire value.

    The 'max' parameter is enforced for each pattern application, so if
    'splitlines' is true, the 'max' setting applies to each line split.
    '''
    @classmethod
    def TYPE(cls):
        return 'split'

    @classmethod
    def fields(cls):
        return ChainMap({'pattern': cls._field('text', default=r'\s+'),
                         'max': cls._field('int', default=0),
                         'splitlines': cls._field('boolean', default=True)},
                        super().fields())

    @cached_property
    def value(self):
        v = super().value
        if v is None:
            return None

        if self.get('splitlines'):
            v = v.splitlines()
        return '\n'.join(chain(*(re.split(self.get('pattern'), buf, maxsplit=self.get('max'))
                                 for buf in v)))


class ConcatReference(TextReference):
    '''ConcatReference object.

    This concatenates multiple reference values.

    The 'source' field must be a list of other references.

    Returns None if all references returned None, otherwise returns
    the concatenated value of all references that provide a value.
    '''
    @classmethod
    def TYPE(cls):
        return 'concat'

    @classmethod
    def fields(cls):
        return ChainMap({'source': cls._field('list')},
                        super().fields())

    @cached_property
    def value(self):
        values = [v for v in map(self.source_text, self.source) if v is not None]
        if not values:
            return None
        return ''.join(values)


class GrepReference(TextReference):
    '''GrepReference object.

    This applies python regex 'search' function, on a line-by-line basis,
    similar to the cmdline 'grep' tool.

    This implementation has additional required keys:
      pattern: The regex pattern to apply

    This implementation has optional keys:
      invert: invert the match (i.e. grep -v)
      count: return only the count of matched lines (i.e. grep -c)
      onlymatching: return only the matched part of each line (i.e. grep -o)
    '''
    @classmethod
    def TYPE(cls):
        return 'grep'

    @classmethod
    def fields(cls):
        return ChainMap({'pattern': cls._field('text'),
                         'invert': cls._field('boolean', default=False),
                         'count': cls._field('boolean', default=False),
                         'onlymatching': cls._field('boolean', default=False,
                                                    conflicts=['invert', 'count'])},
                        super().fields())

    def _line(self, line):
        match = re.search(self.get('pattern'), line)
        if match and self.get('onlymatching'):
            return match.group()
        if match or self.get('invert'):
            return line
        return None

    @cached_property
    def value(self):
        v = super().value
        if v is None:
            return None
        lines = [line for line in map(self._line, v.splitlines(keepends=True))
                 if line is not None]
        if self.get('count'):
            return str(len(lines))
        return ''.join(lines)


class SubstituteReference(TextReference):
    '''SubstituteReference object.

    This applies python regex 'sub' function, on a line-by-line basis.

    This implementation has additional required keys:
      pattern: The regex pattern to apply
      replace: The replacement pattern
    '''
    @classmethod
    def TYPE(cls):
        return 'sub'

    @classmethod
    def fields(cls):
        return ChainMap({'pattern': cls._field('text'),
                         'replace': cls._field('text'),
                         'onlymatching': cls._field('boolean', default=False)},
                        super().fields())

    def _line(self, line):
        if self.get('onlymatching') and not re.search(self.get('pattern'), line):
            return None
        return re.sub(self.get('pattern'), self.get('replace'), line)

    @cached_property
    def value(self):
        v = super().value
        if v is None:
            return None
        return ''.join([line for line in map(self._line, v.splitlines(keepends=True))
                        if line is not None])
