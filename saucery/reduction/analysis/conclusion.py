
from datetime import datetime


class Conclusion(dict):
    def __init__(self, analysis):
        self._analysis = analysis
        start = datetime.now()
        super().__init__({
            'name': analysis.name,
            'level': analysis.level,
            'summary': analysis.summary,
            'description': analysis.description,
            'result': analysis.result,
            'normal': self.normal,
            'abnormal': self.abnormal,
            'unknown': self.unknown,
        })
        end = datetime.now()
        self['duration'] = (end - start).total_seconds()

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

    def __bool__(self):
        # Note that we are only True if our result is abnormal,
        # since only unexpected conclusions need attention.
        # If normal, or if unknown (no conclusion), we are False.
        return self.abnormal
