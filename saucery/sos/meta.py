#!/usr/bin/python3

import json

from collections.abc import MutableMapping
from contextlib import suppress
from copy import copy


class SOSMetaProperty(property):
    def __new__(cls, name, valuetype=str, **kwargs):
        if valuetype == bool:
            cls = BoolSOSMetaProperty
        if isinstance(valuetype, str) and valuetype.lower() == 'json':
            cls = JSONSOSMetaProperty
        return super().__new__(cls)

    def __init__(self, name, valuetype=str, valuelist=False):
        # If valuelist=True, the content is treated as a whitespace-separated list
        self.name = name
        self.cachename = f'_{name}_cache'
        self._valuetype = valuetype
        self.valuelist = valuelist
        super().__init__(self.read, self.write, self.unlink)

    def get_cache(self, sos):
        return getattr(sos, self.cachename)

    def set_cache(self, sos, value):
        setattr(sos, self.cachename, value)

    def del_cache(self, sos):
        with suppress(AttributeError):
            delattr(sos, self.cachename)

    def path(self, sos):
        return sos.workdir / self.name

    def valuetype(self, *args):
        return self._valuetype(*args)

    def value(self, strvalue):
        if self.valuelist:
            with suppress(ValueError):
                return [self.valuetype(v) for v in strvalue.split()]
            return []
        with suppress(ValueError):
            return self.valuetype(strvalue)
        return self.valuetype()

    def strvalue(self, value):
        if isinstance(value, list):
            value = ' '.join(map(self.strvalue, value))
        return str(value or '')

    def _read(self, sos):
        with suppress(AttributeError):
            return self.get_cache(sos)
        with suppress(FileNotFoundError):
            return self.path(sos).read_text()
        return ''

    def read(self, sos):
        return self.value(self._read(sos).strip())

    def write(self, sos, value):
        value = self.strvalue(value)
        if value and '\n' not in value:
            value += '\n'
        self.set_cache(sos, value)
        if not sos.dry_run:
            path = self.path(sos)
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)

    def unlink(self, sos):
        self.del_cache(sos)
        if not sos.dry_run:
            self.path(sos).unlink(missing_ok=True)


class BoolSOSMetaProperty(SOSMetaProperty):
    def valuetype(self, *args):
        return args and str(args[0]).strip().lower() == 'true'

    def strvalue(self, value):
        return str(value is True)


class JSONSOSMetaProperty(SOSMetaProperty):
    def value(self, strvalue):
        if not strvalue:
            return ''
        return json.loads(strvalue)

    def strvalue(self, value):
        if value is None:
            return ''
        return json.dumps(value, indent=2)


class SOSMetaDict(MutableMapping):
    def __init__(self, sos, keys):
        super().__init__()
        self._keys = copy(keys)

        class SOSMeta():
            dry_run = sos.dry_run
            workdir = sos.workdir

        for k in keys:
            setattr(SOSMeta, k, SOSMetaProperty(k))
        self.meta = SOSMeta()

    def __getitem__(self, key):
        if key not in self._keys:
            raise KeyError(key)
        return getattr(self.meta, key)

    def __setitem__(self, key, value):
        if key not in self._keys:
            raise KeyError(key)
        setattr(self.meta, key, value)

    def __delitem__(self, key):
        if key not in self._keys:
            raise KeyError(key)
        delattr(self.meta, key)

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)
