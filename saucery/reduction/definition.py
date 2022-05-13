
import json
import uuid
import yaml

from abc import ABC
from abc import abstractmethod
from collections import UserDict
from contextlib import suppress
from functools import cached_property


class InvalidDefinitionError(Exception):
    pass


class Definition(ABC, UserDict):
    '''Definition object.

    This represents a definition entry.

    The 'definition' must be a dict that contains specific keys.
    Keys common to all implementations are:
      name: Our name (arbitrary value)
      type: Our type (must match a subclass type)
      source: Our source (specific value is implementation-specific)
    '''
    IMPLEMENTATIONS = {}
    ERROR_CLASS = InvalidDefinitionError

    @classmethod
    @abstractmethod
    def TYPE(cls):
        return None

    @staticmethod
    def __new__(cls, definition, *args, **kwargs):
        classtype = definition.get('type')
        if not classtype:
            raise InvalidDefinitionError(f"invalid definition, missing 'type': {definition}")
        subclass = cls.IMPLEMENTATIONS.get(classtype)
        if not subclass:
            raise InvalidDefinitionError(f"Invalid definition, unknown 'type': {classtype}")
        return super().__new__(subclass)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.IMPLEMENTATIONS[cls.TYPE()] = cls

    @classmethod
    def _field(cls, *args, **kwargs):
        return DefinitionField(*args, **kwargs)

    @classmethod
    def fields(cls):
        return {
            'name': cls._field('text'),
            'type': cls._field('text'),
            'source': cls._field(['text', 'list', 'dict']),
        }

    def __init__(self, definition, reductions, *, anonymous=False):
        '''Definition init.

        This requires the definition dict and the SOS reductions we belong to.

        The 'anonymous' param may be set to True if this Definition will be used
        privately by another definition, in which case our 'name' will be generated
        as a random uuid.
        '''
        super().__init__(definition)
        if anonymous:
            self['name'] = str(uuid.uuid4())

        self._reductions = reductions
        reductions[self.name] = self

        self.setup()

    @property
    def sos(self):
        return self._reductions.sos

    @property
    def name(self):
        return self.get('name')

    @property
    def type(self):
        return self.get('type')

    @cached_property
    def source(self):
        s = self.get('source')
        if isinstance(s, dict):
            return self.anonymous(s).name
        return s

    @property
    def json(self):
        return json.dumps(self.data)

    @property
    def yaml(self):
        return yaml.dump(self.data)

    def anonymous(self, definition, *args, **kwargs):
        return Definition(definition, self._reductions, anonymous=True, *args, **kwargs)

    def __repr__(self):
        return self.json

    def _raise(self, msg, *args, **kwargs):
        raise self.ERROR_CLASS(f'{self.__class__.__name__}({self.name}): {msg}', *args, **kwargs)

    def __missing__(self, field):
        if field in self.fields():
            return self.fields().get(field).default
        raise KeyError(field)

    def setup(self):
        if self.get('type') != self.TYPE():
            self._raise(f"type '{self.get('type')}' != '{self.TYPE()}'")

        self.check_invalid_fields()
        self.check_required_fields()
        self.check_conflicting_fields()

        try:
            for field, value in self.items():
                definitionfield = self.fields().get(field)
                self[field] = definitionfield.convert(value)
                definitionfield.check(self[field])
        except InvalidDefinitionError as e:
            self._raise(str(e))

    def check_invalid_fields(self):
        invalid = set(self.keys()) - set(self.fields().keys())
        if invalid:
            self._raise(f"invalid fields: '{','.join(invalid)}'")

    def check_required_fields(self):
        required = set(f for f, v in self.fields().items() if v.default is None)
        missing = required - set(self.keys())
        if missing:
            self._raise(f"required fields: '{','.join(missing)}'")

    def check_conflicting_fields(self):
        for field in self.keys():
            for conflict in (self.fields().get(field).conflicts or []):
                if conflict in self:
                    self._raise(f"conflicting fields: '{field}' and '{conflict}'")


class DefinitionField(object):
    '''DefinitionField class.

    The 'fieldtypes' should be set to a string for required type of
    this field, or a list of possible types. The value must be one of
    the FIELD_TYPES keys.

    If 'fieldtypes' is set to only 'boolean' or only 'int', the value
    will be coerced to a bool or int type value.

    If 'default' is set, it will be used if this field is not set,
    and this field is considered optional; otherwise if 'default' is
    not set, this field is required.

    If 'conflicts' is set, it should be a list of field names this
    field conflicts with.
    '''
    FIELD_CLASSES = {
        'boolean': bool,
        'dict': dict,
        'int': int,
        'list': list,
        'text': str,
    }

    @classmethod
    def field_class(cls, fieldtype):
        try:
            return cls.FIELD_CLASSES[fieldtype]
        except KeyError:
            raise InvalidDefinitionError(f"Invalid field type '{fieldtype}'")

    def __init__(self, fieldtypes, *, default=None, conflicts=None):
        if isinstance(fieldtypes, str):
            fieldtypes = [fieldtypes]
        self.fieldtypes = fieldtypes
        self.fieldclasses = [self.field_class(t) for t in self.fieldtypes]
        self.default = default
        self.conflicts = conflicts or []

    def convert(self, value):
        if value is None:
            return None

        if bool in self.fieldclasses:
            with suppress(Exception):
                value = str(value).strip().lower()
                if value in ('true', 'yes', '1'):
                    return True
                if value in ('false', 'no', '0'):
                    return False

        if int in self.fieldclasses:
            with suppress(Exception):
                return int(value)

        return value

    def check(self, value):
        if value is None:
            return

        if not isinstance(value, tuple(self.fieldclasses)):
            raise InvalidDefinitionError(f"invalid {','.join(self.fieldtypes)} field: '{value}'")
