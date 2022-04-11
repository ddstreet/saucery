
import json

from collections.abc import MutableMapping
from contextlib import suppress
from copy import copy


class SOSMetaProperty(property):
    def __new__(cls, name, valuetype=str, **kwargs):
        if cls == SOSMetaProperty:
            if valuetype == list:
                cls = ListSOSMetaProperty
            if valuetype == bool:
                cls = BoolSOSMetaProperty
        return super().__new__(cls)

    def __init__(self, name, valuetype=str):
        self.name = name
        self.valuetype = valuetype
        super().__init__(self.read, self.write, self.unlink)

    def valuedefault(self):
        return self.valuetype()

    def valueerror(self):
        return ValueError

    def path(self, sos):
        return sos.workdir / self.name

    def value(self, strvalue):
        with suppress(self.valueerror()):
            return self.valuetype(strvalue)
        return self.valuedefault()

    def strvalue(self, value):
        return str(value or '')

    def read(self, sos):
        with suppress(FileNotFoundError):
            return self.value(self.path(sos).read_text().strip())
        return self.value('')

    def write(self, sos, value):
        if not sos.dry_run:
            value = self.strvalue(value)
            if value and '\n' not in value:
                value += '\n'
            path = self.path(sos)
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)

    def unlink(self, sos):
        if not sos.dry_run:
            self.path(sos).unlink(missing_ok=True)


class BoolSOSMetaProperty(SOSMetaProperty):
    def __init__(self, name, valuetype=bool, **kwargs):
        if valuetype != bool:
            raise ValueError(f'Invalid valuetype {valuetype}, must be bool')
        super().__init__(name, valuetype=lambda v: v == 'True', **kwargs)

    def strvalue(self, value):
        return str(value == True)


class ListSOSMetaProperty(SOSMetaProperty):
    def __init__(self, name, valuetype=list, **kwargs):
        if valuetype == list:
            valuetype = str
        super().__init__(name, valuetype=valuetype, **kwargs)

    def value(self, strvalue):
        return [super().value(v) for v in strvalue.split()]

    def strvalue(self, value):
        if isinstance(value, list):
            value = ' '.join(map(self.strvalue, value))
        return super().strvalue(value)


class JsonSOSMetaProperty(SOSMetaProperty):
    def __init__(self, name, valuetype=json, **kwargs):
        if valuetype != json:
            raise ValueError(f'Invalid valuetype {valuetype}, must be json')
        super().__init__(name, valuetype=json.loads, **kwargs)

    def valuedefault(self):
        return None

    def valueerror(self):
        return json.decoder.JSONDecodeError

    def strvalue(self, value):
        return json.dumps(value) if value else ''


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
