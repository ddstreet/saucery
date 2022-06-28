
import logging
import sys

from collections.abc import Sequence
from contextlib import suppress
from functools import cached_property
from pathlib import Path

from ...lines import PathLineOffsets


LOGGER = logging.getLogger(__name__)


class ReferencePath(type(Path())):
    @staticmethod
    def __new__(cls, *args, offset=0, length=0, **kwargs):
        '''The Path class doesn't handle __init__() correctly, so we need this hackery.

        https://github.com/python/cpython/issues/68320
        '''
        self = super().__new__(cls, *args, **kwargs)

        self._offset = max(0, offset)
        self._length = max(0, length)

        self._ref = args[0] if args and isinstance(args[0], ReferencePath) else None

        return self

    @property
    def offset(self):
        if self._ref:
            return self._ref.offset + self._offset
        return self._offset

    @cached_property
    def length(self):
        l = self._length or sys.maxsize
        if self._ref:
            return min(l, max(0, self._ref.length - self._offset))
        with suppress(OSError):
            return min(l, max(0, self.stat().st_size - self._offset))
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

        This returns an iterable of ReferencePath objects, which each represent a line from our value.
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


class ReferencePathList(Sequence):
    def __init__(self, sources):
        self._sources = [s if isinstance(s, ReferencePath) else ReferencePath(s)
                         for s in sources]

    def __getitem__(self, index):
        return self._sources[index]

    def __len__(self):
        return len(self._sources)

    @property
    def length(self):
        return sum([s.length for s in self])

    @property
    def line_iterator(self):
        '''Iterate over our value, line-by-line.

        This returns an iterable of ReferencePath objects, which each represent a line from our value.
        '''
        for referencepath in self:
            yield from referencepath.line_iterator

    @property
    def value(self):
        '''The concatenated value of all ReferencePath objects.

        If all our objects have None value, return None.
        Otherwise, return the concatenated value of all our objects' value as bytes.
        '''
        sources = [s for s in self if s.value is not None]
        if not sources:
            return None
        return b''.join([s.value for s in sources])

    def _slice(self, offset, length):
        length = length or sys.maxsize
        for referencepath in self:
            if referencepath.length <= offset:
                offset -= referencepath.length
            else:
                r = ReferencePath(referencepath, offset=offset, length=length)
                length -= r.length
                yield r
            if length <= 0:
                break

    def slice(self, offset, length=0):
        return ReferencePathList(list(self._range(offset, length)))
