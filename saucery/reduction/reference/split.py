
from .parse import ParseReference


class SplitlinesReference(ParseReference):
    '''SplitlinesReference class.

    Split the pathlist value by lines.
    '''
    @classmethod
    def TYPE(cls):
        return 'splitlines'

    def parse(self, pathlist):
        return pathlist.line_pathlist
