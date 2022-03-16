
import logging
import subprocess

from collections import UserDict
from copy import copy
from functools import cached_property


class LookupBase(UserDict):
    LOGGER = logging.getLogger(__name__)
    SUBCLASSES = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        cls.SUBCLASSES.append(cls)

    def lookup_value(self, key, formatmap):
        self.LOGGER.debug(f"No value for '{key}'")
        return None

    def _log_lookup_key(self, key, fallback=None):
        value = self.get(key, fallback)
        if not value:
            self.LOGGER.error(f'Missing config: {key}')
        return value

    @cached_property
    def lookup_order(self):
        return self._log_lookup_key('lookup_order', '').split()

    @cached_property
    def lookup_keys(self):
        return self._log_lookup_key('lookup_keys', '').split()

    def lookup(self, **kwargs):
        '''Lookup value(s) from our config file.

        This performs lookups from our config file and returns the resulting
        value(s) as a dict of key: value pairs.

        The 'lookup_order' config value is split() and each key used to lookup
        a value through the lookup_value() method, which will call through all
        subclasses that are part of this instance. The initial format map contains
        the key: value pairs provided as kwargs. As each value is looked up, it
        is converted to str() and added as a key: value pair into the format map.

        The 'lookup_keys' config value is split() and each key used to form
        a final dict() that is returned from this method. The values are pulled
        from the format map values.

        If any lookup_value() returns None, lookup stops and this returns {}.

        The intention of this class is to allow flexible configuration in our
        config file, that can build on the results of previous operations, to
        craft a final result that is returned to the caller in a generic way.

        On success, returns a dict() of key: value pairs, with all keys being
        exactly what is listed in the value of the 'lookup_keys' lookup. On
        failure, returns {}.
        '''
        if not self.lookup_order:
            self.LOGGER.debug(f'missing lookup_order')
            return {}
        if not self.lookup_keys:
            self.LOGGER.debug(f'missing lookup_keys')
            return {}
        fmtmap = {**kwargs}
        for key in self.lookup_order:
            value = self.lookup_value(key, fmtmap)
            if value is None:
                return {}
            fmtmap[key] = str(value)
        self.LOGGER.debug(f'lookup result: {fmtmap}')
        return {k: fmtmap.get(k) for k in self.lookup_keys}


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
    def _lookup_globals(self):
        return copy(globals())

    @cached_property
    def _lookup_locals(self):
        return copy(locals())

    def _lookup_python(self, key, formatmap):
        cmd = self.get(key)
        if not cmd:
            return None
        cmd = cmd.format(**formatmap)
        self.LOGGER.debug(f"lookup_python '{key}': {cmd}")
        try:
            return eval(cmd, self._lookup_globals, self._lookup_locals)
        except Exception as e:
            self.LOGGER.error(f'Error running lookup cmd: {e}')
            return None

    def lookup_value(self, key, formatmap):
        value = self._lookup_python(f'python_{key}', formatmap)
        if value is None:
            return super().lookup_value(key, formatmap)
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
    def _subprocess_timeout(self):
        return self.get('subprocesslookup_timeout', 30)

    def _lookup_subprocess(self, key, formatmap):
        cmd = self.get(key)
        if not cmd:
            return None
        cmd = ast.literal_eval(cmd)
        self.LOGGER.debug(f"lookup_subprocess '{key}': {cmd}")
        if not isinstance(cmd, list):
            self.LOGGER.error(f'Invalid lookup cmd (not a list): {cmd}')
            return None
        cmd = [c.format(**formatmap) for c in cmd]
        try:
            result = subprocess.run(cmd, encoding='utf-8',
                                    timeout=self._subprocess_timeout,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            self.LOGGER.error(f'Timed out waiting for lookup cmd')
            return None
        if result.returncode != 0:
            self.LOGGER.error(f'Error running lookup cmd: {result.stderr}')
            return None
        return result.stdout

    def lookup_value(self, key, formatmap):
        value = self._lookup_subprocess(f'subprocess_{key}', formatmap)
        if value is None:
            return super().lookup_value(key, formatmap)
        return value


class ConstLookup(LookupBase):
    '''Lookup const value from config.

    The lookup key must use the prefix 'const_'.

    If the key is found in the config, its value is used.

    If the key is not found in the config, None is returned.
    '''
    def _lookup_const(self, key, formatmap):
        value = self.get(key)
        if value:
            self.LOGGER.debug(f"lookup_const '{key}': {value}")
        return value

    def lookup_value(self, key, formatmap):
        value = self._lookup_const(f'const_{key}', formatmap)
        if value is None:
            return super().lookup_value(key, formatmap)
        return value


class ConfigLookup(*LookupBase.SUBCLASSES):
    pass
