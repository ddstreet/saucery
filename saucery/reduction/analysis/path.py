
from abc import abstractmethod
from functools import cached_property


class ReferencePathListResult(object):
    def __init__(self, pathlist):
        self._pathlist = pathlist
        self._value = pathlist.value if pathlist else None

    def path_detail(self, path):
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

    def path_filter(self, path):
        '''If this ReferencePath should be included in the result details.

        By default, this returns True if the path value is not None; otherwise False.
        '''
        return path.value is not None

    @cached_property
    def details(self):
        '''The result details.

        Returns a list of ResultDetail objects.
        '''
        return list(map(self.path_detail, filter(self.path_filter, self._pathlist or [])))

    @property
    def _expected(self):
        '''If the result detail(s) are as expected.

        This controls the 'normal' and 'abnormal' states.

        By default, if we have no result details, this returns True; otherwise False.
        Subclasses may override this if needed.
        '''
        return not bool(self.details)

    @property
    def normal(self):
        '''If the results are normal.

        Returns True if the results are 'normal'.

        This returns True if self.unknown is False and self._expected is True;
        otherwise False. Subclasses should normally not need to override this.

        Note that when this is True, neither abnormal nor unknown are True.
        '''
        return not self.unknown and bool(self._expected)

    @property
    def abnormal(self):
        '''If the results are abnormal.

        Returns True if the results are 'not normal', indicating they should be examined.

        This returns True if self.unknown is False and self._expected is False;
        otherwise False. Subclasses should normally not need to override this.

        Note that when this is True, neither normal nor unknown are True.
        '''
        return not self.unknown and not bool(self._expected)

    @property
    def unknown(self):
        '''If the results are unknown.

        Returns True if the analysis could not be performed.

        By default, if our pathlist value is None, this returns True; otherwise False.
        Subclasses may override this if needed.

        Note that when this is True, neither normal nor abnormal are True.
        '''
        return self._value is None


class ReferencePathDictResult(ReferencePathListResult):
    def __init__(self, pathdict):
        super().__init__(pathdict.pathlist if pathdict else None)
        self._pathdict = pathdict


class ComparisonPathListResult(ReferencePathListResult):
    def path_filter(self, path):
        return super().path_filter(path) and self.path_compare(path)

    @abstractmethod
    def path_compare(self, path):
        pass
