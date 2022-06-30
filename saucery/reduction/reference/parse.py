
import subprocess

from abc import abstractmethod
from collections import ChainMap
from functools import cached_property
from shutil import which

from .path import ReferencePathList
from .reference import Reference


class ParseReference(Reference):
    '''ParseReference object.

    This base class should be used by any class that performs processing on another Reference.

    The 'source' parameter must be a text string containing the name of a Reference.

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
        source = self.reductions.reference(self.source)
        pathlist = getattr(source, 'pathlist', None)
        if not self.parse_none_value:
            if pathlist is None or pathlist.value is None:
                return None

        return self.parse(pathlist)


class TransformReference(ParseReference):
    '''TransformReference object.

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
        value = getattr(pathlist, 'value', None)
        if not self.parse_none_value and value is None:
            return None

        name = self.get('name')

        self.sos.analysis_files[name] = self.transform(value)

        return ReferencePathList([self.sos.analysis_files.path(name)])


class ExecReference(TransformReference):
    '''ExecReference object.

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
    def fields(cls):
        return ChainMap({'source': cls._field('text', default=''),
                         'exec': cls._field('text'),
                         'params': cls._field(['text', 'list'], default=[])},
                        super().fields())

    def setup(self):
        super().setup()
        # Find our exec binary
        self.exec_cmd

    @property
    def parse_none_value(self):
        # Allow exec without any source
        # e.g. to use external program to process the entire sos filesdir/
        return not self.source

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
    '''JqReference object.

    This extends ExecReference, and sets the default of the 'exec' field to 'jq'.

    This requires the jq parsing str to be provided in the 'jq' field.

    Unlike ExecReference, this does require a value source to parse.
    '''
    @classmethod
    def TYPE(cls):
        return 'jq'

    @classmethod
    def fields(cls):
        return ChainMap({'source': cls._field('text'),
                         'exec': cls._field('text', default='jq'),
                         'jq': cls._field('text')},
                        super().fields())

    @property
    def exec_cmd(self):
        return super().exec_cmd + [self.get('jq')]
