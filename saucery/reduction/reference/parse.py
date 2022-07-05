
import subprocess

from abc import abstractmethod
from functools import cached_property
from shutil import which

from .path import ReferencePathDict
from .path import ReferencePathList
from .reference import ReferenceSourceReference


class ParseReference(ReferenceSourceReference):
    '''ParseReference class.

    This base class should be used by any class that performs processing on another Reference.

    Implementations should put all processing work in parse() using the passed ReferencePathList,
    and returning a processed ReferencePathList.
    '''
    @abstractmethod
    def parse(self, pathlist):
        '''Parse the pathlist.

        Subclasses must implement this. The return value must be a ReferencePathList, or None.

        This will only be called once, and the returned list cached.

        The 'pathlist' parameter will never be None.

        If self.parse_none_value is False (the default), the pathlist.value will never be None.
        '''
        pass

    @property
    def parse_none_value(self):
        '''If a None parameter should be provided to parse().

        If False (the default), the parse() method will not be called if the pathlist provided
        to it is None, or if the pathlist.value is None. If True, parse() will be called even
        if the pathlist or pathlist.value is None.
        '''
        return False

    @cached_property
    def pathlist(self):
        if not self.parse_none_value and self.source_value is None:
            return None

        return self.parse(self.source_pathlist)


class TransformReference(ParseReference):
    '''TransformReference class.

    This operates similarly to ParseReference, except subclasses should implement the transform()
    method, and return the transformed value as bytes, or None.

    This will create a new ReferencePath to store the transformed value.
    '''
    @abstractmethod
    def transform(self, value):
        '''Transform the value.

        Subclasses must implement this. The return value must be bytes, or None.

        This will only be called once, and the returned value cached.

        If self.parse_none_value is False (the default), the value will never be None.
        '''
        pass

    def parse(self, pathlist):
        value = pathlist.value if pathlist else None
        if not self.parse_none_value and value is None:
            return None

        name = self.get('name')

        self.sos.analysis_files[name] = self.transform(value)

        return ReferencePathList([self.sos.analysis_files.path(name)], sos=self.sos)


class ExecReference(TransformReference):
    '''ExecReference class.

    This extends TransformReference, and runs an external program to transform the source value.

    The 'exec' field must be the name of the program to run, and 'params' should (optionally)
    be either a single str param value or list of str param values. Any {}-style format fields
    in any of the params will be replaced with the value of field from the sos, for example
    {filesdir} will be replaced with the actual full path of the sos.filesdir.

    Unlike most References, the 'source' field is optional, in which case no stdin will be
    provided to the external program. If the 'source' field is provided, the external
    program will only be called if the source reference provides a value.
    '''
    @classmethod
    def TYPE(cls):
        return 'exec'

    @classmethod
    def _add_fields(cls):
        return {
            'source': str,
            'exec': str,
            'params': [str, list],
        }

    @classmethod
    def _field_defaults(cls):
        return {
            'source': '',
            'params': [],
        }

    def setup(self):
        super().setup()
        # Find our exec binary
        self.exec_cmd

    @property
    def parse_none_value(self):
        # Allow exec without any source, if 'source' field is unset
        # e.g. to use external program to process the entire sos filesdir/
        return not self.get('source')

    @cached_property
    def exec_cmd(self):
        cmd = which(self.get('exec'))
        if not cmd:
            self._raise("Could not find '{self.get('exec')}' command")
        return [cmd] + self.sos.mapping.format(self.get('params'))

    def transform(self, value):
        result = subprocess.run(self.exec_cmd, input=value,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        if result.returncode != 0:
            return None
        return result.stdout


class JqReference(ExecReference):
    '''JqReference class.

    This extends ExecReference, and sets the default of the 'exec' field to 'jq'.

    This requires the jq parsing str to be provided in the 'jq' field.

    Unlike ExecReference, this does require a value source to parse.
    '''
    @classmethod
    def TYPE(cls):
        return 'jq'

    @classmethod
    def _add_fields(cls):
        return {
            'source': str,
            'exec': str,
            'jq': str,
        }

    @classmethod
    def _field_defaults(cls):
        return {
            'exec': 'jq',
        }

    @property
    def exec_cmd(self):
        return super().exec_cmd + [self.get('jq')]


class DictReference(ParseReference):
    '''DictReference class.

    This parses the source ReferencePathList into a ReferencePathDict.

    Subclasses should perform parsing in the parse() method, but importantly must return
    a ReferencePathDict (not a ReferencePathList).
    '''
    @cached_property
    def pathdict(self):
        '''ReferencePathDict object.

        This returns the ReferencePathDict generated by the subclass in the parse() method.
        '''
        pathdict = super().pathlist
        if not isinstance(pathdict, (ReferencePathDict, type(None))):
            self._raise('DictReference class must return ReferencePathDict from parse()')

        return pathdict

    @property
    def pathlist(self):
        return self.pathdict.pathlist if self.pathdict else None
