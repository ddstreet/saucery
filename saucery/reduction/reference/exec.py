
import subprocess

from collections import ChainMap
from functools import cached_property

from .path import ReferencePathList
from .reference import Reference


class ExecReference(Reference):
    @classmethod
    def TYPE(cls):
        return 'exec'

    @classmethod
    def fields(cls):
        return ChainMap({'params': cls._field(['text', 'list'], default=[])},
                        super().fields())

    @property
    def cmd(self):
        return [self.source] + self.sos.mapping.format(self.get('params'))

    def exec(self):
        result = subprocess.run(self.cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        if result.returncode != 0:
            return None
        return result.stdout

    @cached_property
    def pathlist(self):
        self.sos.analysis_files[self.name] = self.exec()

        return ReferencePathList([self.sos.analysis_files.path(self.name)])
