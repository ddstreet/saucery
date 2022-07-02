
import re

from .parse import ParseReference


class RegexReference(ParseReference):
    '''RegexReference class.

    The 'pattern' field must be a python regex pattern, which will be matched to our source
    value. This will create a new pathlist containing only matched section(s).

    The 'multiline' field sets the regex MULTILINE mode. It is True by default.

    The 'ignorecase' field sets the regex IGNORECASE mode. It is False by default.
    '''
    @classmethod
    def TYPE(cls):
        return 'regex'

    @classmethod
    def _add_fields(cls):
        return {
            'pattern': 'bytes',
            'multiline': 'bool',
            'ignorecase': 'bool',
        }

    @classmethod
    def _field_default(cls, field):
        return {
            'multiline': True,
            'ignorecase': False,
        }.get(field, super()._field_default(field))

    @property
    def _pattern(self):
        return self.get('pattern')

    @property
    def _flags(self):
        flags = 0
        if self.get('multiline'):
            flags |= re.MULTILINE
        if self.get('ignorecase'):
            flags |= re.IGNORECASE
        return flags

    def parse(self, pathlist):
        return pathlist.regex_pathlist(self._pattern, self._flags)
