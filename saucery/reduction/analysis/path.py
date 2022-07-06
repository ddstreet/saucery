
from functools import cached_property


class ReferencePathListResult(object):
    def __init__(self, pathlist):
        self._pathlist = pathlist
        self._value = pathlist.value if pathlist else None

    def result_detail(self, path):
        return {
            'description': '{0}',
            '0': {
                'text': path.value,
                'path': path.sospath,
                'offset': path.offset,
                'length': path.length,
                'first_line': path.first_line_number,
                'last_line': path.last_line_number,
            },
        }

    @cached_property
    def details(self):
        '''The result details.

        Returns a list of ResultDetail objects.
        '''
        return [self.result_detail(p) for p in self._pathlist or [] if p.value is not None]

    @property
    def normal(self):
        '''If the results are normal.

        Returns True if the results are 'normal'.

        The default implementation here returns True if abnormal and unknown are False,
        and False otherwise.

        Note that when this is True, neither abnormal nor unknown are True.
        '''
        return not self.unknown and not self.abnormal

    @property
    def abnormal(self):
        '''If the results are abnormal.

        Returns True if the results are 'not normal', indicating they should be examined.

        The default implementation here returns True if our value is not None/empty,
        and False otherwise.

        Note that when this is True, neither normal nor unknown are True.
        '''
        return bool(self._value)

    @property
    def unknown(self):
        '''If the results are unknown.

        Returns True if the analysis could not be performed.

        The default implementation here returns True if our value is None,
        and False otherwise.

        Note that when this is True, neither normal nor abnormal are True.
        '''
        return self._value is None
