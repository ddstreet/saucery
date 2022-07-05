
import logging
import re
import sys

from collections.abc import Collection
from collections.abc import Mapping
from contextlib import suppress
from functools import cached_property
from pathlib import Path

from ...lines import PathLineOffsets


LOGGER = logging.getLogger(__name__)


class ReferencePath(type(Path())):
    @staticmethod
    def __new__(cls, *args, sos=None, offset=0, length=0, **kwargs):
        '''The Path class doesn't handle __init__() correctly, so we need this hackery.

        https://github.com/python/cpython/issues/68320
        '''
        self = super().__new__(cls, *args, **kwargs)

        self._sos = sos
        self._offset = max(0, offset)
        self._length = max(0, length)

        self._ref = args[0] if args and isinstance(args[0], ReferencePath) else None

        if not self._ref and not self._sos:
            raise ValueError('ReferencePath requires SOS')

        # Raise ValueError if not inside our sos
        self.sospath

        return self

    @property
    def sos(self):
        return self._sos or self._ref._sos

    @property
    def sospath(self):
        return self.relative_to(self.sos.workdir)

    @property
    def offset(self):
        if self._ref:
            return self._ref.offset + self._offset
        return self._offset

    @cached_property
    def length(self):
        maxlen = self._length or sys.maxsize
        if self._ref:
            return max(min(self._ref.length - self._offset, maxlen), 0)
        with suppress(OSError):
            return max(min(self.stat().st_size - self._offset, maxlen), 0)
        return 0

    def slice(self, offset, length=0):
        return ReferencePath(self, offset=offset, length=length)

    @cached_property
    def _path_line_offsets(self):
        if self._ref:
            return self._ref._path_line_offsets
        return PathLineOffsets(self)

    @cached_property
    def _line_number_range(self):
        return self._path_line_offsets.line_range(self.offset, self.length)

    @property
    def first_line_number(self):
        '''The line number containing the start of our range.

        Note this may be greater than 1, if our offset is non-zero.
        '''
        return self._line_number_range[0]

    @property
    def last_line_number(self):
        '''The line number containing the end of our range.

        Note this may be less than our file's last line number.
        '''
        return self._line_number_range[1]

    @property
    def line_iterator(self):
        '''Iterate over our value, line-by-line.

        This returns an iterable of ReferencePath objects, which each represent a line.
        '''
        offsets = self._path_line_offsets.line_offsets
        if offsets is None:
            return

        offsets = [o - self.offset for o in offsets if o > self.offset]
        if not offsets:
            return

        pos = 0
        for o in offsets:
            yield ReferencePath(self, offset=pos, length=o - pos)
            pos = o

    def regex_iterator(self, pattern, flags=0):
        '''Iterate over our value, returning matches for the provided regex pattern.

        This returns an iterable of ReferencePath objects, which each represent a
        section of our value that matches the regex pattern.

        This will *not* include any 'null' (0-length) matches.
        '''
        if pattern is None:
            return
        if isinstance(pattern, str):
            pattern = pattern.encode(errors='replace')
        if not isinstance(pattern, bytes):
            raise ValueError(f'Requires str or bytes, not {type(pattern)}')
        for match in re.finditer(pattern, self.value, flags=flags):
            matchlen = match.end() - match.start()
            if not matchlen:
                continue
            yield ReferencePath(self, offset=match.start(), length=matchlen)

    @cached_property
    def _value(self):
        with suppress(OSError):
            with self.open(mode='rb', buffering=0) as f:
                f.seek(self.offset)
                return f.read(self._length or None)
        return None

    @property
    def value(self):
        '''Value of this reference source in bytes.

        Returns bytes from our file, starting at our offset and continuing
        until our specified length or the end of the file.

        On error, return None.
        '''
        if self._ref:
            offset = self.offset - self._ref.offset
            end_offset = offset + self.length
            return self._ref.value[offset:end_offset]
        return self._value


class ReferencePathList(Collection):
    def __init__(self, paths, sos=None):
        self._paths = [p if isinstance(p, ReferencePath) else ReferencePath(p, sos=sos)
                       for p in paths]

    def __contains__(self, item):
        return item in iter(self)

    def __iter__(self):
        return iter(self._paths)

    def __len__(self):
        return len(self._paths)

    @property
    def length(self):
        return sum([p.length for p in self._paths])

    @property
    def line_iterator(self):
        '''Iterate over our value, line-by-line.

        This returns an iterable of ReferencePath objects, which each represent a line.
        '''
        for referencepath in self._paths:
            yield from referencepath.line_iterator

    @property
    def line_pathlist(self):
        '''ReferencePathList of each line in our value.

        This returns our line_iterator wrapped in a new ReferencePathList.
        '''
        return ReferencePathList(self.line_iterator)

    def regex_iterator(self, pattern, flags=0):
        '''Iterate over our value, returning matches for the provided regex pattern.

        This returns an iterable of ReferencePath objects, which each represent a
        section of our value that matches the regex pattern.

        This will *not* include any 'null' (0-length) matches.
        '''
        for referencepath in self._paths:
            yield from referencepath.regex_iterator(pattern, flags=flags)

    def regex_pathlist(self, pattern, flags=0):
        '''ReferencePathList of each match of our value for the pattern.

        This returns our regex_iterator wrapped in a new ReferencePathList.
        '''
        return ReferencePathList(self.regex_iterator(pattern, flags=flags))

    @property
    def value(self):
        '''The concatenated value of all ReferencePath objects.

        If we have no objects, return an empty bytes.

        If we have at least one object and all our objects' value is None, return None.

        Otherwise, return the concatenated value of all our objects' value as bytes.
        '''
        values = [p.value for p in self._paths if p.value is not None]
        if not values and self._paths:
            return None
        return b''.join(values)

    def _slice(self, offset, length):
        length = length or sys.maxsize
        for referencepath in self._paths:
            if referencepath.length <= offset:
                offset -= referencepath.length
            else:
                r = ReferencePath(referencepath, offset=offset, length=length)
                length -= r.length
                yield r
            if length <= 0:
                break

    def slice(self, offset, length=0):
        return ReferencePathList(list(self._slice(offset, length)))


class ReferencePathDict(ReferencePathList, Mapping):
    '''ReferencePathDict class.

    This provides a key-value mapping to two values; both a processed value, and the
    ReferencePath backing the processed key-value pair.
    '''
    def __init__(self, paths):
        '''Initialize the instance.

        Unlike the ReferencePathList constructor, the 'paths' parameter must be a dict where
        each key maps to a 2-tuple value; the first entry in the tuple is the processed value,
        while the second entry in the tuple is the ReferencePath.

        When accessed as a Mapping, using either [key] or get(key), this will return the
        processed value. To access the ReferencePath for a key, use path(key).
        '''
        self._paths_dict = paths

    @cached_property
    def _paths(self):
        return [v[1] for v in self._paths_dict.values()]

    @cached_property
    def pathlist(self):
        return ReferencePathList(self._paths)

    def path(self, key):
        return self._paths_dict[key][1]

    def __getitem__(self, key):
        return self._paths_dict[key][0]

    def __iter__(self):
        return iter(self._paths_dict.keys())
