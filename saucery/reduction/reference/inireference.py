
from collections import ChainMap
from collections import UserDict
from configparser import ConfigParser
from functools import cached_property

from .parse import ParseReference


class IniReference(ParseReference):
    NO_DEFAULT_SECTION = '_SAUCERY_NO_DEFAULT_SECTION_'

    @classmethod
    def TYPE(cls):
        return 'ini'

    def setup(self):
        super().setup()
        self._line = None
        self._section = None
        self._sections = {}

    @property
    def sections(self):
        # Force parsing by referencing value
        self.value
        return self._sections

    def _line_iterator(self, lines):
        for l in lines:
            self._line = l
            yield l.value.decode(errors='replace')
        self._line = None
        self._section = None

    def parse(self, pathlist):
        parser = None
        class dictcls(dict):
            def __getitem__(innerself, key):
                value = super().__getitem__(key)
                if self._line and isinstance(value, dict):
                    self._section = self._sections[key]
                return value

            def __setitem__(innerself, key, value):
                super().__setitem__(key, value)
                if not self._line:
                    return
                if isinstance(value, dict):
                    self._sections[key] = IniSection(parser, key, self._line)
                    self._section = self._sections[key]
                elif isinstance(value, list) or value is None:
                    self._section[key] = IniOption(self._section, key, self._line)

        parser = ConfigParser(default_section=self.NO_DEFAULT_SECTION,
                              strict=False, dict_type=dictcls)
        parser.read_file(self._line_iterator(pathlist.line_iterator), self.name)

        return pathlist


class IniSection(UserDict):
    def __init__(self, parser, name, line):
        super().__init__()
        self._parser = parser
        self._name = name
        self._line = line

    @property
    def name(self):
        return self._name

    @property
    def referencepath(self):
        return self._line


class IniOption(object):
    def __init__(self, section, key, line):
        super().__init__()
        self._parser = section._parser
        self._section = section
        self._key = key
        self._line = line

    @property
    def value(self):
        return self._parser[self._section.name][self._key]

    @property
    def referencepath(self):
        return self._line
