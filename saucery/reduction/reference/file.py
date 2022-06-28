
from collections import ChainMap
from itertools import chain
from functools import cached_property
from pathlib import Path

from .path import ReferencePathList
from .reference import Reference


class FileReference(Reference):
    '''FileReference object.

    This represents a reference to file(s) inside the SOS.

    The 'source' must be either a single file path or a list of file paths.

    Each 'source' file path may be a regular string path, or may use
    python 'glob' syntax; specifically, Path.glob() syntax:
    https://docs.python.org/3/library/pathlib.html#pathlib.Path.glob

    The result of any 'glob' expansion will be sorted.

    This has additional optional keys:
      noglob: If True, globbing is disabled (default False)
    '''
    @classmethod
    def TYPE(cls):
        return 'file'

    @classmethod
    def fields(cls):
        return ChainMap({'noglob': cls._field('boolean', default=False),
                         'source': cls._field(['text', 'list'])},
                        super().fields())

    @property
    def source(self):
        source = super().source
        if not isinstance(source, list):
            return [source]
        return source

    @cached_property
    def pathlist(self):
        if self.get('noglob'):
            sources = [self.file(s) for s in self.source]
        else:
            sources = list(chain(*(self.fileglob(s) for s in self.source)))
        return ReferencePathList([s for s in sources if s])

    def _convert_source(self, source):
        return source

    def file(self, source):
        return self.sos.file(self._convert_source(source))

    def fileglob(self, path):
        return sorted(self.sos.fileglob(self._convert_source(source)) or [])


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

    def _convert_source(self, source):
        return str(Path(self.get('subdir')) / source.lstrip('/'))


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

    def file(self, source):
        return self.sos.file(self._convert_source(source),
                             command=self.get('command'))

    def fileglob(self, path):
        return sorted(self.sos.fileglob(self._convert_source(source),
                                        command=self.get('command')) or [])


class AnalysisFileReference(Reference):
    '''AnalysisFileReference object.

    This represents a reference to a file under analysis_files/.

    The 'source' must be a single filename; this does not allow use of globs.
    '''
    @classmethod
    def TYPE(cls):
        return 'analysis_file'

    @cached_property
    def pathlist(self):
        return ReferencePathList([self.sos.analysis_file(self.source)])
