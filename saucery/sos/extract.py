
import logging
import tarfile
import tempfile

from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SOSExtractionError(Exception):
    pass


class SOSExtraction(object):
    def __init__(self, sos):
        self.sos = sos
        self.members = []

    def add_member(self, path, membertype, **kwargs):
        self.members.append(SOSExtractionMember(path, membertype, **kwargs))

    def get_members(self, membertype):
        return [m for m in self.members if m.get('type') == membertype]

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
        relpath = Path(*path.relative_to(dest).parts[1:])
        if not str(path).startswith(str(dest)):
            self.warning(f"Skipping invalid member path '{m.name}'")
            self.add_member(relpath, 'invalid')
        elif m.isdir():
            path.mkdir(mode=0o775)
            self.add_member(relpath, 'dir')
        elif getattr(m, 'linkname', None):
            if not str(path.parent.joinpath(m.linkname).resolve()).startswith(str(dest)):
                self.warning(f"Skipping invalid file '{m.name}' link '{m.linkname}'")
            path.symlink_to(m.linkname)
            self.add_member(relpath, 'link', link=m.linkname)
        elif m.ischr():
            self.debug(f"Ignoring char node '{m.name}'")
            self.add_member(relpath, 'chr')
        elif m.isblk():
            self.debug(f"Ignoring block node '{m.name}'")
            self.add_member(relpath, 'blk')
        elif m.isfifo():
            self.debug(f"Ignoring fifo node '{m.name}'")
            self.add_member(relpath, 'fifo')
        elif m.isfile():
            if tar.fileobj.tell() != m.offset_data:
                self.warning(f'tar offset {tar.fileobj.tell()} != '
                             f'member data offset {m.offset_data}')
                tar.fileobj.seek(m.offset_data)
            path.write_bytes(tar.fileobj.read(m.size))
            mode = path.stat().st_mode
            path.chmod(mode | 0o644)
            self.add_member(relpath, 'file', size=m.size)
        else:
            self.debug(f"Ignoring unknown type '{m.type}' member '{m.name}'")
            self.add_member(relpath, 'unknown')

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


class SOSExtractionMember(dict):
    def __init__(self, path, membertype, **kwargs):
        super().__init__(name=path.name, path=str(path), type=membertype, **kwargs)
