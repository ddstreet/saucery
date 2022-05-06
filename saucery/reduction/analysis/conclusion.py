
from collections.abc import Mapping
from functools import cached_property


class Conclusion(Mapping):
    def __init__(self, analysis):
        self._analysis = analysis

    @cached_property
    def data(self):
        '''Get the data for this conclusion.

        This is created outside of the constructor so the instance can be created
        without actually performing the analysis, which is done lazily when the
        conclusion result or normal state is actually accessed.
        '''
        return {
            'name': self.analysis.name,
            'level': self.analysis.level,
            'summary': self.analysis.summary,
            'description': self.analysis.description,
            'result': self.analysis.result,
            'duration': self.analysis.duration.total_seconds(),
            'normal': self.normal,
            'abnormal': self.abnormal,
            'unknown': self.unknown,
        }

    def __getitem__(self, key):
        return self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    @property
    def analysis(self):
        return self._analysis

    @property
    def normal(self):
        return self.analysis.normal is True

    @property
    def abnormal(self):
        return self.analysis.normal is False

    @property
    def unknown(self):
        return self.analysis.normal is None
