
import logging
import subprocess


LOGGER = logging.getLogger(__name__)


class SOSSquashError(Exception):
    pass


class SOSSquash(object):
    '''Squash and/or mount extracted SOS files/ tree.'''
    def __init__(self, sos):
        self._sos = sos

    @property
    def sos(self):
        return self._sos

    def squash(self):
        src = self.sos.filesdir
        dest = self.sos.squashimg
        cmd = ['mksquashfs', str(src), str(dest), '-quiet', '-no-progress']
        result = subprocess.run(cmd, encoding='utf-8',
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stdout.strip():
            LOGGER.debug(result.stdout)
        if result.returncode != 0:
            if result.stderr.strip():
                LOGGER.error(result.stderr)
            raise SOSSquashError(f'Could not squash {src} to {dest}')

    def mount(self):
        src = self.sos.squashimg
        dest = self.sos.filesdir
        dest.mkdir(exist_ok=True)
        cmd = ['squashfuse', '-o', 'allow_other', str(src), str(dest)]
        result = subprocess.run(cmd, encoding='utf-8',
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stdout.strip():
            LOGGER.debug(result.stdout)
        if result.returncode != 0:
            if result.stderr.strip():
                LOGGER.error(result.stderr)
            raise SOSSquashError(f'Could not mount {src} at {dest}')

    def unmount(self):
        mount = self.sos.filesdir
        cmd = ['umount', str(mount)]
        result = subprocess.run(cmd, encoding='utf-8',
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stdout.strip():
            LOGGER.debug(result.stdout)
        if result.returncode != 0:
            if result.stderr.strip():
                LOGGER.error(result.stderr)
            raise SOSSquashError(f'Could not unmount {mount}')
