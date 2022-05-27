
import logging
import tarfile
import tempfile

from collections import defaultdict
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SOSExtractionError(Exception):
    pass


class SOSExtraction(object):
    def __init__(self, sos):
        self.sos = sos
        self._paths = defaultdict(list)
        self.file_sizes = []

    def paths(self, name):
        return self._paths[name]

    @property
    def file_paths(self):
        return self.paths('file')

    @property
    def dir_paths(self):
        return self.paths('dir')

    @property
    def link_paths(self):
        return self.paths('link')

    @property
    def relative_file_paths(self):
        return ['/'.join(p.parts[1:]) for p in self.file_paths]

    def extract(self):
        if not self.sos.workdir.exists():
            self.sos.workdir.mkdir(parents=False, exist_ok=False)

        try:
            with tempfile.TemporaryDirectory(dir=self.sos.workdir) as tmpdir:
                self.extract_to(Path(tmpdir).resolve())
        except Exception as e:
            raise SOSExtractionError(e)

    def extract_to(self, dest):
        top = None
        with tarfile.open(self.sos.sosreport) as tar:
            for m in tar:
                mtop = m.name.split('/')[0]
                if not top:
                    top = mtop
                elif top != mtop:
                    raise ValueError(f'Multiple top-level dirs: {top}, {mtop}')
                self.extract_member(dest, tar, m)
        if not top:
            raise ValueError('No files found in sosreport')

        # Rename 'tmpdir/sosreport-.../' to 'files/'
        dest.joinpath(top).rename(self.sos.filesdir)

    def extract_member(self, dest, tar, m):
        path = dest.joinpath(m.name).resolve()
        relpath = path.relative_to(dest)
        if not str(path).startswith(str(dest)):
            self.warning(f"Skipping invalid member path '{m.name}'")
            self.paths('invalid').append(relpath)
        elif m.isdir():
            path.mkdir(mode=0o775)
            self.paths('dir').append(relpath)
        elif getattr(m, 'linkname', None):
            if not str(path.parent.joinpath(m.linkname).resolve()).startswith(str(dest)):
                self.warning(f"Skipping invalid file '{m.name}' link '{m.linkname}'")
            path.symlink_to(m.linkname)
            self.paths('link').append(relpath)
        elif m.ischr():
            self.debug(f"Ignoring char node '{m.name}'")
            self.paths('chr').append(relpath)
        elif m.isblk():
            self.debug(f"Ignoring block node '{m.name}'")
            self.paths('blk').append(relpath)
        elif m.isfifo():
            self.debug(f"Ignoring fifo node '{m.name}'")
            self.paths('fifo').append(relpath)
        elif m.isfile():
            if tar.fileobj.tell() != m.offset_data:
                self.warning(f'tar offset {tar.fileobj.tell()} != '
                             f'member data offset {m.offset_data}')
                tar.fileobj.seek(m.offset_data)
            path.write_bytes(tar.fileobj.read(m.size))
            mode = path.stat().st_mode
            path.chmod(mode | 0o644)
            self.paths('file').append(relpath)
            self.file_sizes.append(m.size)
        else:
            self.debug(f"Ignoring unknown type '{m.type}' member '{m.name}'")
            self.paths('unknown').append(relpath)

    def _log(self, lvl, fmt, *args):
        LOGGER.log(lvl, f'{fmt}: {self.sos.name}', *args)

    def error(self, *args):
        self._log(logging.ERROR, *args)

    def warning(self, *args):
        self._log(logging.WARNING, *args)

    def info(self, *args):
        self._log(logging.INFO, *args)

    def debug(self, *args):
        self._log(logging.DEBUG, *args)
