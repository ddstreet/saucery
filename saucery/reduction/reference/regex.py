
import re

from .parse import ParseReference


class RegexReference(ParseReference):
    '''RegexReference class.

    The 'regex' field must be a python regex pattern, which will be matched to our source
    value. This will create a new pathlist containing only matched section(s).
    '''
    @classmethod
    def TYPE(cls):
        return 'regex'

    @classmethod
    def fields(cls):
        return ChainMap({'regex': cls._field('text')},
                        super().fields())

    def parse(self, pathlist):
        return pathlist.regex_pathlist(self.get('regex')))
