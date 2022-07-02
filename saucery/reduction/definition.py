
import inspect
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
      name: Our name (string, arbitrary value)
      type: Our type (string, must match a subclass type)
      source: Our source (string by default, implementation-specific value)
    '''
    ABSTRACT_SUBCLASSES = {}
    SUBCLASSES = {}
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
        subclass = cls.SUBCLASSES.get(classtype)
        if not subclass:
            abstract_subclass = cls.ABSTRACT_SUBCLASSES.get(classtype)
            if abstract_subclass:
                raise InvalidDefinitionError(f"Invalid definition, type '{classtype}' is abstract")
            raise InvalidDefinitionError(f"Invalid definition, type '{classtype}' is unknown")
        return super().__new__(subclass)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not inspect.isabstract(cls):
            cls.SUBCLASSES[cls.TYPE()] = cls
        elif cls.TYPE():
            cls.ABSTRACT_SUBCLASSES[cls.TYPE()] = cls

    @classmethod
    def _add_fields(cls):
        '''Fields to add for this class.

        Subclasses should NOT call super()!
        '''
        return {
            'name': str,
            'type': str,
            'source': str,
        }

    @classmethod
    def _remove_fields(cls):
        '''Fields to remove for this class.

        Subclasses should NOT call super()!
        '''
        return None

    @classmethod
    def _fields(cls):
        fields = {}
        for c in reversed(inspect.getmro(cls)):
            if not issubclass(c, Definition):
                continue
            with suppress(KeyError):
                func = '_add_fields'
                if not isinstance(c.__dict__[func], classmethod):
                    raise cls.ERROR_CLASS(f'{c.__name__}.{func} must be a classmethod')
                fields.update(getattr(c, func)() or {})
            with suppress(KeyError):
                func = '_remove_fields'
                if not isinstance(c.__dict__[func], classmethod):
                    raise cls.ERROR_CLASS(f'{c.__name__}.{func} must be a classmethod')
                for f in getattr(c, func)() or []:
                    fields.pop(f, None)
        return fields

    @classmethod
    def _field_default(cls, field):
        return None

    @classmethod
    def _field_conflicts(cls, field):
        return None

    @cached_property
    def fields(self):
        return {k: DefinitionField(v,
                                   default=self._field_default(k),
                                   conflicts=self._field_conflicts(k))
                for k, v in self._fields().items()}

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
        reductions[self.get('name')] = self

        self.setup()

    @property
    def reductions(self):
        return self._reductions

    @property
    def sos(self):
        return self.reductions.sos

    @cached_property
    def source(self):
        return self.get('source')

    @property
    def json(self):
        return json.dumps(self.data)

    @property
    def yaml(self):
        return yaml.dump(self.data)

    def anonymous(self, definition, *args, **kwargs):
        return Definition(definition, self.reductions, anonymous=True, *args, **kwargs)

    def __repr__(self):
        return self.json

    def _raise(self, msg, *args, **kwargs):
        clsname = self.__class__.__name__
        name = self.get('name')
        raise self.ERROR_CLASS(f'{clsname}({name}): {msg}', *args, **kwargs)

    def __missing__(self, field):
        if field in self.fields:
            return self.fields.get(field).default
        raise KeyError(field)

    def setup(self):
        if self.get('type') != self.TYPE():
            self._raise(f"type '{self.get('type')}' != '{self.TYPE()}'")

        self.check_invalid_fields()
        self.check_required_fields()
        self.check_conflicting_fields()

        try:
            for field, value in self.items():
                definitionfield = self.fields.get(field)
                self[field] = definitionfield.convert(value)
                definitionfield.check(self[field])
        except InvalidDefinitionError as e:
            self._raise(str(e))

    def check_invalid_fields(self):
        invalid = set(self.keys()) - set(self.fields.keys())
        if invalid:
            self._raise(f"invalid fields: '{','.join(invalid)}'")

    def check_required_fields(self):
        required = set(f for f, v in self.fields.items() if v.default is None)
        missing = required - set(self.keys())
        if missing:
            self._raise(f"required fields: '{','.join(missing)}'")

    def check_conflicting_fields(self):
        for field in self.keys():
            for conflict in (self.fields.get(field).conflicts or []):
                if conflict in self:
                    self._raise(f"conflicting fields: '{field}' and '{conflict}'")


class DefinitionSourceDefinition(Definition):
    '''DefinitionSourceDefinition class.

    This requires the 'source' field to be a str name of a Definition.
    '''
    @property
    def source(self):
        '''Return the source Definition.

        Unlike Definition.source, this returns the source Definition instead of the
        'source' field value. If the source Definition is not found, this returns None.
        '''
        return self.reductions.get(super().source)

    @property
    def source_class(self):
        '''The required class our source must be.

        This should return a class or list of classes.
        '''
        return Definition

    def setup(self):
        super().setup()

        source_classes = self.source_class
        if not isinstance(source_classes, list):
            source_classes = [source_classes]
        if not isinstance(self.source, tuple(source_classes + [type(None)])):
            clsname = self.source.__class__.__name__
            classes = ' or '.join([c.__name__ for c in source_classes])
            self._raise(f'Source class is {clsname} but we require {classes}')


class DefinitionField(object):
    '''DefinitionField class.

    The 'fieldtypes' should be set to a string for required type of
    this field, or a list of possible types. The value must be one of
    the FIELD_TYPES keys.

    If 'fieldtypes' is set to only one of 'bool', 'int', 'text', or 'bytes',
    the value will be coerced to that type. If 'list' is one of the
    field types, the value will always be converted to a list.

    If 'default' is set, it will be used if this field is not set,
    and this field is considered optional; otherwise if 'default' is
    not set, this field is required.

    If 'conflicts' is set, it should be a list of field names this
    field conflicts with.
    '''
    FIELD_CLASSES = [
        bool,
        bytes,
        dict,
        int,
        list,
        str,
    ]

    def __init__(self, fieldclasses, *, default=None, conflicts=None):
        if not isinstance(fieldclasses, list):
            fieldclasses = [fieldclasses]
        for c in fieldclasses:
            if c not in self.FIELD_CLASSES:
                raise InvalidDefinitionError(f"Invalid field class '{c}'")
        self.fieldclasses = set(fieldclasses)
        self.default = default
        self.conflicts = conflicts or []

    @property
    def fieldnames(self):
        return [c.__name__ for c in self.fieldclasses]

    def convert(self, value):
        if value is None:
            return None

        if set([bool]) == self.fieldclasses:
            with suppress(Exception):
                value = str(value).strip().lower()
                if value in ('true', 'yes', '1'):
                    return True
                if value in ('false', 'no', '0'):
                    return False

        if set([int]) == self.fieldclasses:
            with suppress(Exception):
                return int(value)

        if set([str]) == self.fieldclasses:
            if isinstance(value, bytes):
                with suppress(Exception):
                    return value.decode()
            else:
                with suppress(Exception):
                    return str(value)

        if set([bytes]) == self.fieldclasses:
            if isinstance(value, str):
                with suppress(Exception):
                    return value.encode()
            else:
                with suppress(Exception):
                    return bytes(value)

        if list in self.fieldclasses:
            if not isinstance(value, list):
                value = [value]

        return value

    def check(self, value):
        if not isinstance(value, tuple(self.fieldclasses) + (None,)):
            raise InvalidDefinitionError(f"invalid {','.join(self.fieldnames)} field: '{value}'")
