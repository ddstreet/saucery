
import subprocess

from collections import ChainMap
from shutil import which

from .transform import TransformValueReference


class JqReference(TransformValueReference):
    @classmethod
    def TYPE(cls):
        return 'jq'

    @classmethod
    def fields(cls):
        return ChainMap({'jq': cls._field('text'),
                         'raw': cls._field('boolean', default=False),
                         'env': cls._field('text', default='')},
                        super().fields())

    def setup(self):
        super().setup()
        self._jq = which('jq')
        if not self._jq:
            self._raise("requires 'jq' command, please install jq package.")

    @property
    def jqcmd(self):
        cmd = [self._jq]
        if self.get('raw'):
            cmd.append('-r')
        cmd.append(self.get('jq'))
        return cmd

    def transform_value(self, value):
        result = subprocess.run(self.jqcmd, input=value,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        if result.returncode != 0:
            return None
        return result.stdout
