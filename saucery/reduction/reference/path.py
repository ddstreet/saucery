
import logging

from collections.abc import Sequence
from contextlib import suppress
from functools import cached_property
from pathlib import Path

from ...sos.lines import PathLineOffsets


LOGGER = logging.getLogger(__name__)


class ReferencePath(Path):
    def __init__(self, path, *, offset=0, length=0):
        super.__init__(str(path))
        self._offset = max(0, offset)
        self._length = max(0, length)

    @property
    def offset(self):
        return self._offset

    @cached_property
    def length(self):
        '''Length of our file content.

        This returns our internal length, if set; otherwise this attempts to
        detect the size of our file, and returns its size minus our offset.

        If our internal length is not set and we cannot detect our file size,
        return 0.

        This should not be used to detect missing files; use the value attribute instead.
        '''
        if self._length:
            return self._length
        with suppress(OSError):
            return max(0, self.stat().st_size - self.offset)
        return 0

    def range(self, start, length=0):
        return ReferencePath(self, offset=start, length=length)

    @cached_property
    def line_number_range(self):
        '''Line number(s) corresponding to our offset/length.

        This behaves exactly as PathLineOffsets.line_range(), using our offset and length.
        '''
        return PathLineOffsets(self).line_range(self.offset, self.length)

    @property
    def first_line_number(self):
        '''The line number containing the start of our range.'''
        return self.line_number_range[0]

    @property
    def last_line_number(self):
        '''The line number containing the end of our range.'''
        return self.line_number_range[1]

    @cached_property
    def value(self):
        '''Value of this reference source in bytes.

        Returns bytes from our file, starting at our offset and continuing
        until our specified length or the end of the file.

        On error, return None.
        '''
        with suppress(OSError):
            with self.open(mode='rb', buffering=0) as f:
                f.seek(self.offset)
                return f.read(self._length or None)
        return None


class TextReferencePath(ReferencePath):
    @property
    def length(self):
        return len(self.value or '')

    def range(self, offset, length=0):
        LOGGER.warning('TextReferencePath.range() not implemented, fixme!')
        return super().range(offset, length)

    @cached_property
    def value(self):
        v = super().value
        if v is None:
            return None
        return v.decode(errors='replace')


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
    def value(self):
        '''The concatenated value of all ReferencePath objects.

        If all our objects have None value, return None.
        Otherwise, return the concatenated value of all our objects' value as bytes.
        '''
        sources = [s for s in self if s.value is not None]
        if not sources:
            return None
        return b''.join([s.value for s in sources])

    def _range(self, start, length):
        length = length or sys.maxsize
        for source in self:
            if source.length <= start:
                start -= source.length
                continue
            offset = source.offset + start
            start = 0
            yield ReferencePath(source, offset=offset, length=min(length, source.length))
            length -= source.length
            if length <= 0:
                return

    def range(self, start, length=0):
        return ReferencePathList(list(self._range(start, length)))
