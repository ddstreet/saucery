
import json as _json_

from json import *
from pathlib import Path


def dumps(*args, **kwargs):
    kwargs.setdefault('cls', SauceryJSONEncoder)
    return _json_.dumps(*args, **kwargs)


class SauceryJSONEncoder(_json_.JSONEncoder):
    def default(self, o):
        if isinstance(o, bytes):
            return o.decode()
        if isinstance(o, Path):
            return str(o)
        return super().default(o)
