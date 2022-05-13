
import os
import subprocess

from collections import ChainMap
from shutil import which

from .textreference import TextReference


class JqReference(TextReference):
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
    def jqenv(self):
        env = {}
        if self.get('env'):
            env = self.anonymous({'type': 'jsondict', 'source': self.get('env')}).dict or {}
        return ChainMap(env, os.environ)

    @property
    def jqcmd(self):
        cmd = [self._jq]
        if self.get('raw'):
            cmd.append('-r')
        cmd.append(self.get('jq'))
        return cmd

    def jq(self, value):
        result = subprocess.run(self.jqcmd, env=self.jqenv, encoding='utf-8',
                                input=value,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        if result.returncode != 0:
            return None
        return result.stdout

    @property
    def value(self):
        v = super().value
        if v is None:
            return None
        return self.jq(v)
