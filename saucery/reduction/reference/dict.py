
import configparser

from collections import ChainMap
from collections import UserDict
from functools import cached_property

from .parse import DictReference
from .parse import ParseReference
from .path import ReferencePathDict


class IniReference(ParseReference):
    '''IniReference class.

    This parses its source value as a INI file, which should be in the default format
    accepted by the python ConfigParser class.

    Note that this does not modify the provided ReferencePathList; the parsed content
    must be accessed using the 'sections' attribute, which returns a dict containing
    key-value pairs; the keys are all parsed section names and each maps to a IniSection
    object.
    '''
    NO_DEFAULT_SECTION = '_SAUCERY_NO_DEFAULT_SECTION_'

    @classmethod
    def TYPE(cls):
        return 'ini'

    @classmethod
    def _add_fields(cls):
        return {
            'default_section': 'text',
        }

    @classmethod
    def _field_default(cls, field):
        return {
            'default_section': configparser.DEFAULTSECT,
        }.get(field, super()._field_default(field))

    def setup(self):
        super().setup()
        self._line = None
        self._section = None
        self._sections = {}

    @property
    def sections(self):
        # Force parsing by referencing pathlist
        self.pathlist
        return self._sections

    @cached_property
    def defaultsection(self):
        return self.sections.get(self.get('default_section'), {})

    def section(self, name):
        s = self.sections.get(name)
        if s is None:
            return None
        d = self.defaultsection
        return ReferencePathDict(ChainMap({k: (v.value, v.referencepath) for k, v in s.items()},
                                          {k: (v.value, v.referencepath) for k, v in d.items()}))

    def _line_iterator(self, lines):
        for line in lines:
            self._line = line
            yield line.value.decode(errors='replace')
        self._line = None
        self._section = None

    def parse(self, pathlist):
        parser = None

        class dictcls(dict):
            def __getitem__(innerself, key):
                value = super().__getitem__(key)
                if self._line and isinstance(value, innerself.__class__):
                    self._section = self._sections[key]
                return value

            def __setitem__(innerself, key, value):
                super().__setitem__(key, value)
                if not self._line:
                    return
                if isinstance(value, innerself.__class__):
                    self._sections[key] = IniSection(parser, key)
                    self._section = self._sections[key]
                elif isinstance(value, list) or value is None:
                    self._section[key] = IniOption(self._section, key, self._line)

        # We need to use a fake default_section name, so we can detect the real default section
        parser = configparser.ConfigParser(default_section=self.NO_DEFAULT_SECTION,
                                           strict=False, dict_type=dictcls,
                                           interpolation=None)
        parser.read_file(self._line_iterator(pathlist.line_iterator), self.get('name'))

        return pathlist


class IniSectionReference(IniReference, DictReference):
    '''IniSectionReference class.

    This extends IniReference, but provides a single INI section's dict as its pathdict.
    '''
    @classmethod
    def TYPE(cls):
        return 'inisection'

    @classmethod
    def _add_fields(cls):
        return {
            'section': 'text',
        }

    @property
    def sections(self):
        # Do not force parsing by referencing pathlist, as we're called by parse()
        return self._sections

    @property
    def _section_name(self):
        return self.get('section')

    def parse(self, pathlist):
        super().parse(pathlist)
        return self.section(self._section_name)


class KeyValueDictReference(IniSectionReference):
    '''KeyValueDictReference class.

    This parses its source value as simple key-value pairs.

    The source value should be in the format of a single INI file section, which generally
    is simple 'key=value' assignments, one per line. See the ConfigParser class for more
    specific details on the expected format.
    '''
    @classmethod
    def TYPE(cls):
        return 'keyvaluedict'

    @classmethod
    def _remove_fields(cls):
        return ['section', 'default_section']

    @property
    def _section_name(self):
        return '_KEY_VALUE_SECTION_'

    def _line_iterator(self, lines):
        # Set _line so our section is created
        self._line = True
        yield f'[{self._section_name}]'
        yield from super()._line_iterator(lines)


class IniSection(UserDict):
    def __init__(self, parser, name):
        super().__init__()
        self._parser = parser
        self._name = name

    @property
    def name(self):
        return self._name


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
