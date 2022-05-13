
from collections import ChainMap
from functools import cached_property

from .transform import IndirectReference


class BytesReference(IndirectReference):
    '''BytesReference object.

    This encodes the source Reference value from str to bytes.

    This implementation has optional keys:
      encoding: The encoding to use (default 'utf-8')
      errors: The error handling to use (default 'backslashreplace')

    If the source Reference value is already bytes, this passes it
    along unmodified.
    '''
    @classmethod
    def TYPE(cls):
        return 'bytes'

    @classmethod
    def fields(cls):
        return ChainMap({'encoding': cls._field('text', default='utf-8'),
                         'errors': cls._field('text', default='backslashreplace')},
                        super().fields())

    @cached_property
    def value(self):
        return self.source_bytes(encoding=self.get('encoding'), errors=self.get('errors'))
