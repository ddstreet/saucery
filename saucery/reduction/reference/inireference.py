
from collections import ChainMap
from configparser import ConfigParser
from functools import cached_property

from .dictreference import DictReference
from .reference import FileReference


class IniReference(DictReference, FileReference):
    @classmethod
    def TYPE(cls):
        return 'ini'

    @cached_property
    def parser(self):
        p = ConfigParser(strict=False)
        p.read(self.paths)
        return p

    @cached_property
    def dict(self):
        return dict(self.parser.items())


class IniSectionReference(IniReference):
    @classmethod
    def TYPE(cls):
        return 'inisection'

    @classmethod
    def fields(cls):
        return ChainMap({'section': cls._field('text')},
                        super().fields())

    @cached_property
    def dict(self):
        section = super().dict.get(self.get('section'))
        if not section:
            return None
        return dict(section)
