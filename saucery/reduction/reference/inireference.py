
from collections import ChainMap
from configparser import ConfigParser
from functools import cached_property

from .reference import Reference


class IniReference(Reference):
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
