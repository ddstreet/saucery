
from contextlib import suppress
from functools import partial
from pathlib import Path


class PathLineOffsets(Path):
    '''Detect the offset of each line in a file.

    This always starts with offset 0 indicating the start of the first line,
    then the offset of the first byte of each new line.

    The final offset is always the total file size, which can be used to determine
    the end of the final line.
    '''
    DIRNAME = '.SAUCERY_LINES'
    BLOCKSIZE = 4 * 1024 * 1024

    @classmethod
    def line_offsets_path(cls, path):
        return path.parent / cls.DIRNAME / path.name

    def __init__(self, path):
        super().__init__(self.line_offsets_path(path))
        self._source = path

    @property
    def source(self):
        return self._source

    def line(self, offset):
        '''The line number for an offset.

        Returns the 1-based line number for the specified offset,
        or None if the offset is outside our offset range or we could
        not determine our offsets.
        '''
        line = 0
        for o in self.line_offsets or []:
            if o > offset:
                break
            line += 1
        else:
            return None
        return line

    def last_line(self):
        '''Our file's last line number.

        Returns the line number of the last line in our file, or None if we could not determine
        our offsets.
        '''
        offsets = self.line_offsets
        if not offsets:
            return None
        return len(offsets) - 1

    def line_range(self, offset, length):
        '''The lines containing the specified bytes.

        Returns a two-tuple of line numbers. The first entry is the same as self.line(offset).
        The second entry is the line number containing the final byte in the range, or our
        last line number.

        Returns (None, None) if the range starts outside our offsets, or if we could not detect
        our offsets.
        '''
        return (self.line(offset), self.line(offset + max(length, 1) - 1) or self.last_line)

    @cached_property
    def line_offsets(self):
        '''The file's line offsets.

        Returns a list of our file's line offsets.
        '''
        try:
            return self.read_text().strip().split(',')
        except OSError:
            return self.detect_offsets()

    def detect_offsets(self):
        '''Detect the offsets.

        This returns the offsets in the same format as line_offsets, but it
        does not cache the result nor does it save the result to file.
        '''
        with suppress(OSError):
            offsets = [0]
            pos = 0
            with self.source.open('rb') as f:
                for block in iter(partial(f.read, self.BLOCKSIZE), b''):
                    offsets += [pos + n.end() for n in re.finditer(b'\n', block)]
                    pos += len(block)
            if offsets[-1] != pos:
                offsets.append(pos)
            return offsets
        return None