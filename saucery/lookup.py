
import logging
import subprocess

from copy import copy
from functools import cached_property


class LookupBase(object):
    LOGGER = logging.getLogger(__name__)
    SUBCLASSES = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        cls.SUBCLASSES.append(cls)

    def __init__(self, config, name):
        super().__init__()
        self.config = config
        self.name = name

    def lookup_key(self, key, formatmap):
        self.LOGGER.debug(f"No value for '{key}'")
        return None

    @property
    def lookup_start_key(self):
        return self.config.get(f'{self.name}_start_key', 'key')

    @property
    def lookup_order(self):
        return self.config.get(f'{self.name}_lookup_order', '').split()

    @property
    def lookup_keys(self):
        return self.config.get(f'{self.name}_lookup_keys', '').split()

    def lookup(self, start_value):
        fmtmap = {self.lookup_start_key: start_value}
        for key in self.lookup_order:
            value = self.lookup_key(key, fmtmap)
            if value is None:
                return None
            fmtmap[key] = str(value)
        self.LOGGER.debug(f'lookup result: {fmtmap}')
        return {k: fmtmap.get(k) for k in self.lookup_keys}


class ConstLookup(LookupBase):
    '''Lookup const value from config.

    The lookup key must use the prefix 'const_'.

    If the key is found in the config, its value is used.

    If the key is not found in the config, None is returned.
    '''
    def lookup_const(self, key, formatmap):
        value = self.config.get(key)
        self.LOGGER.debug(f"lookup_const '{key}': {value}")
        return value

    def lookup_key(self, key, formatmap):
        value = self.lookup_const(f'const_{key}', formatmap)
        if value is None:
            return super().lookup_key(key, formatmap)
        return value


class SubprocessLookup(LookupBase):
    '''Lookup value from subprocess call.

    The lookup key must use the prefix 'subprocess_'. The value must be a
    python list, which will be passed directly to subprocess.

    The list string will be evaluated with ast.literal_eval(), and then each
    string in the list will be formatted using the format map, so any literal
    { or } characters in the command must be doubled (i.e. {{ or }}).

    The result returncode should be 0 if successfully looked up or if
    no result was found. The result returncode should be nonzero if there
    was a failure and stderr should include the text of the failure, which
    will be logged, and None returned.

    On success, the subprocess stdout should be the str result, or if there was no
    result found, the stdout should be empty.
    '''
    @property
    def subprocess_timeout(self):
        return self.config.get('subprocesslookup_timeout', 30)

    def lookup_subprocess(self, key, formatmap):
        cmd = self.config.get(key)
        self.LOGGER.debug(f"lookup_subprocess '{key}': {cmd}")
        if not cmd:
            return None
        cmd = ast.literal_eval(cmd)
        if not isinstance(cmd, list):
            self.LOGGER.error(f'Invalid lookup cmd (not a list): {cmd}')
            return None
        cmd = [c.format(**formatmap) for c in cmd]
        try:
            result = subprocess.run(cmd, encoding='utf-8',
                                    timeout=self.subprocess_timeout,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            self.LOGGER.error(f'Timed out waiting for lookup cmd')
            return None
        if result.returncode != 0:
            self.LOGGER.error(f'Error running lookup cmd: {result.stderr}')
            return None
        return result.stdout

    def lookup_key(self, key, formatmap):
        value = self.lookup_subprocess(f'subprocess_{key}', formatmap)
        if value is None:
            return super().lookup_key(key, formatmap)
        return value


class PythonLookup(LookupBase):
    '''Lookup value from python eval.

    The lookup key must use the prefix 'python_'. The value must python
    code that will be passed directly to eval(). Copies of the running
    globals() and locals() will be stored by this class instance and passed
    to each call to eval.

    The string will first be formatted using the format map, so any literal
    { or } characters in the command must be doubled (i.e. {{ or }}).

    On failure, the python code should raise an Exception, which will be caught
    and the exception error logged, and None will be returned for this lookup.

    On success, the return value of the call to eval() should be the str-type result.

    If no error occurred, but no result was found, the return value should be ''.
    '''
    @cached_property
    def globals(self):
        return copy(globals())

    @cached_property
    def locals(self):
        return copy(locals())

    def lookup_python(self, key, formatmap):
        cmd = self.config.get(key)
        self.LOGGER.debug(f"lookup_python '{key}': {cmd}")
        if not cmd:
            return None
        cmd = cmd.format(**formatmap)
        try:
            return eval(cmd, self.globals, self.locals)
        except Exception as e:
            self.LOGGER.error(f'Error running lookup cmd: {e}')
            return None

    def lookup_key(self, key, formatmap):
        value = self.lookup_python(f'python_{key}', formatmap)
        if value is None:
            return super().lookup_key(key, formatmap)
        return value


class ConfigLookup(*LookupBase.SUBCLASSES):
    pass
