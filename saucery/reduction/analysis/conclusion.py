
import json

from functools import cached_property


class Conclusion(object):
    def __init__(self, analysis):
        super().__init__()
        self._analysis = analysis

    @cached_property
    def data(self):
        return {
            'name': self.analysis.name,
            'level': self.analysis.level,
            'summary': self.analysis.summary,
            'description': self.analysis.description,
            'result': self.analysis.result,
            'normal': self.normal,
        }

    @property
    def analysis(self):
        return self._analysis

    @property
    def normal(self):
        return self.analysis.normal

    def __repr__(self):
        return json.dumps(self.data)

    def __bool__(self):
        # Note that we are only True if our result is *not* normal,
        # since only unexpected conclusions need attention.
        # If normal, or if None (no conclusion), we are False.
        return self.normal is False
