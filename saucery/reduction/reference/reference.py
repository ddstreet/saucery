
import bz2
import gzip
import lzma

from abc import abstractmethod
from collections import ChainMap
from functools import cached_property
from itertools import chain
from pathlib import Path

from saucery.reduction.definition import Definition
from saucery.reduction.definition import InvalidDefinitionError


__all__ = [
    'InvalidReferenceError',
    'Reference',
]


class InvalidReferenceError(InvalidDefinitionError):
    pass


class Reference(Definition):
    '''Reference object.

    This represents a reference to an entry inside the SOS.
    '''
    ERROR_CLASS = InvalidReferenceError

    @classmethod
    def _value_bytes(cls, value, **kwargs):
        return cls._value_convert(value, False, **kwargs)

    @classmethod
    def _value_text(cls, value, **kwargs):
        return cls._value_convert(value, True, **kwargs)

    @classmethod
    def _value_convert(cls, value, to_text, **kwargs):
        if value is None:
            return None
        if to_text and isinstance(value, str):
            return value
        if not to_text and isinstance(value, bytes):
            return value
        params = {k: v for k, v in kwargs.items() if v is not None}
        if to_text:
            return value.decode(**params)
        return value.encode(**params)

    @property
    def _value_conversion_kwargs(self):
        return {}

    @property
    def value_bytes(self):
        return self._value_bytes(self.value, **self._value_conversion_kwargs)

    @property
    def value_text(self):
        return self._value_text(self.value, **self._value_conversion_kwargs)

    @property
    @abstractmethod
    def value(self):
        '''The value.'''
        return None


class FileReference(Reference):
    '''FileReference object.

    This represents a reference to file(s) inside the SOS.

    The 'source' must be either a single file path or a list of file paths.

    Each 'source' file path may be a regular string path, or may use
    python 'glob' syntax; specifically, Path.glob() syntax:
    https://docs.python.org/3/library/pathlib.html#pathlib.Path.glob

    The result of any 'glob' expansion will be sorted.

    The file is transparently decompresssed if the suffix is recognized.

    This has additional optional keys:
      noglob: If True, globbing is disabled (default False)
    '''
    @classmethod
    def TYPE(cls):
        return 'file'

    @classmethod
    def fields(cls):
        return ChainMap({'noglob': cls._field('boolean', default=False)},
                        super().fields())

    @classmethod
    def decompressors(cls):
        return {
            'bz2': bz2.decompress,
            'gz': gzip.decompress,
            'xz': lzma.decompress
        }

    @classmethod
    def decompressor(cls, suffix):
        return cls.decompressors().get(suffix.lower().lstrip('.'), lambda b: b)

    @classmethod
    def decompress(cls, path, content=None):
        if content is None:
            content = path.read_bytes()

        try:
            return cls.decompressor(path.suffix)(content)
        except Exception as e:
            print(f'Could not decompress {path}: {e}')

        return None

    @classmethod
    def path_read(cls, path, decompress=True):
        if not path or not path.is_file():
            return None

        try:
            content = path.read_bytes()
        except PermissionError:
            return None

        if not decompress:
            return content

        return cls.decompress(path, content)

    def _relative_sospath(self, path):
        return str(Path('/') / path.relative_to(self.sos.filesdir))

    @property
    def _subdir(self):
        return ''

    @cached_property
    def basepath(self):
        return self.sos.filesdir / self._source(self._subdir)

    def _source(self, source):
        return str(source).lstrip('/')

    @property
    def sources(self):
        sources = self.source
        if isinstance(sources, str):
            return [sources]
        return sources

    def _expand_glob(self, path):
        if self.get('noglob'):
            return [self.basepath / path]
        return self.basepath.glob(path)

    @cached_property
    def paths(self):
        return chain(*(sorted(self._expand_glob(s))
                       for s in map(self._source, self.sources)))

    @cached_property
    def value(self):
        content = [c for c in [self.path_read(p) for p in self.paths] if c is not None]
        if not content:
            return None
        return b''.join(content)


class SubdirFileReference(FileReference):
    '''SubdirFileReference object.

    This represents a reference to file(s) under a subdir in the sosreport.

    The only difference from FileReference is the 'source' path(s) are
    resolved under 'subdir' inside the sosreport.

    This implementation has additional required keys:
      subdir: The subdirectory to use
    '''
    @classmethod
    def TYPE(cls):
        return 'subdirfile'

    @classmethod
    def fields(cls):
        return ChainMap({'subdir': cls._field('text')},
                        super().fields())

    @property
    def _subdir(self):
        return self.get('subdir')


class CommandReference(FileReference):
    '''CommandReference object.

    This represents a reference to a sos_commands file(s) inside the SOS.

    This is identical to SubdirFileReference, except this class uses
    'command' parameter which expands to a subdir of sos_commands/'command'/.

    This implementation has additional required keys:
      command: The 'sos_commands' subdir command
    '''
    @classmethod
    def TYPE(cls):
        return 'command'

    @classmethod
    def fields(cls):
        return ChainMap({'command': cls._field('text')},
                        super().fields())

    @property
    def _subdir(self):
        return str(Path('/sos_commands') / self.get('command'))


class SOSMetaReference(Reference):
    '''SOSMetaReference object.

    This represents a reference to a 'meta' property of the SOS instance.

    This gets the value of self.sos.meta.get(source) or None.
    '''
    @classmethod
    def TYPE(cls):
        return 'sosmeta'

    @property
    def value(self):
        return self.sos.meta.get(self.source)
