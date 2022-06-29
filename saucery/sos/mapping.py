
from collections.abc import Mapping


class SOSMapping(Mapping):
    def __init__(self, sos):
        self.sos = sos

    def __getitem__(self, key):
        try:
            return getattr(self.sos, key)
        except AttributeError:
            raise KeyError(key)

    def __iter__(self):
        return (a for a in dir(self.sos) if not a.startswith('_'))

    def __len__(self):
        return len(list(self))

    def format(self, params):
        return [p.format_map(self) for p in params]
