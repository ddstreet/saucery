
import logging
import shutil
import subprocess
import tarfile
import tempfile

from contextlib import suppress
from functools import cached_property
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SOSExtractionError(Exception):
    pass


class SOSExtraction(object):
    '''Extract SOS object (tarball) to SOS files/ dir.'''
    def __init__(self, sos):
        self._sos = sos
        self._members = {}

    @property
    def _journal_output_path(self):
        # TODO: this should be made a config value, maybe with this value as default
        return 'sos_commands/logs/journal'

    @property
    def sos(self):
        return self._sos

    @property
    def members(self):
        '''Extracted member data.

        The 'members' list contains dict entries for each extracted member,
        with each entry containing fields:
        - name (filename, without path)
        - path (full relative path, without leading dir)
        - type (member type, e.g. 'file', 'dir', etc)

        Additionally, some types contain additional fields:
        - size (file size, only for 'file' types)
        - link (link target, only for 'link' types)
        '''
        return list(self._members.values())

    def get_members(self, membertype):
        return [m for m in self.members if m.get('type') == membertype]

    def extract(self):
        '''Extract the sosreport.

        This may add, remove, or modify the extracted files.

        This may leave the files directly on the filesystem, or may
        repackage the extracted files into an image and r/o mount that
        at the files/ dir.
        '''
        destdir = self.sos.filesdir.parent
        if not destdir.exists():
            destdir.mkdir(parents=False, exist_ok=False)

        try:
            with tempfile.TemporaryDirectory(dir=destdir) as tmpdir:
                # Extract and rename 'tmpdir/sosreport-.../' to 'files/'
                path = self._extract_to(Path(tmpdir).resolve())
                self._process(path)
                path.rename(self.sos.filesdir)
        except Exception as e:
            raise SOSExtractionError(e)

    def _extract_to(self, dest):
        '''Extract to destination dir.

        If our SOS contains more than 1 top-level dir (i.e. more than just one
        top-level 'sosreport-*' dir), or nothing at all, this raises SOSExtractionError.

        Callers should not expect the name of the returned path to exactly match the
        SOS tarball top-level dir name.

        Returns a Path to the extracted top-level dir.
        '''
        toplevel = None
        with tarfile.open(self.sos.sosreport) as tar:
            for m in tar:
                member = SOSExtractionMember(dest, m)
                self._members[member.get('path')] = dict(member)
                if not toplevel:
                    toplevel = member.toplevel
                if toplevel != member.toplevel:
                    raise ValueError(f'Multiple top-level dirs: {toplevel}, {member.toplevel}')
                self._extract_member(tar, member)
        if not toplevel:
            raise ValueError('Nothing found in sosreport')
        return dest / toplevel

    def _extract_member(self, tar, member):
        path = member.path
        if member.invalid_path:
            self.warning(f"Skipping invalid member path '{path}'")
        elif member.invalid_link:
            self.warning(f"Skipping invalid member '{path}' link '{member.get('link')}'")
        elif not member.extract(tar):
            self.debug(f"Ignoring {member.type} member '{path}'")

    def _process(self, path):
        if self._extract_journal(path):
            self._remove_journal(path)

    def _read_machineid(self, dest):
        try:
            path = dest.joinpath('etc/machine-id')
        except FileNotFoundError:
            path = dest.joinpath('var/lib/dbus/machine-id')
        return path.read_text().strip()

    def _extract_journal(self, dest):
        try:
            machine_id = self._read_machineid(dest)
        except FileNotFoundError:
            self.info('Could not find machine-id, skipping journal processing')
            return False

        journaldir = dest / 'var/log/journal' / machine_id
        if not journaldir.exists():
            self.info(f'No journal dir for {machine_id}, skipping journal processing')
            return False

        self.info('Converting binary journals to text')

        output = dest / self._journal_output_path
        cmd = ['journalctl', '--no-pager', '--system', '-o', 'with-unit', '-D', str(journaldir)]
        with output.open(mode='wb') as o:
            result = subprocess.run(cmd, stdout=o, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.error('Failed to extract journal, skipping')
            if result.stderr.strip():
                self.error(result.stderr)
            return False
        self._members[self._journal_output_path] = {
            'name': output.name,
            'path': self._journal_output_path,
            'type': 'file',
            'size': output.stat().st_size,
        }
        return True

    def _remove_journal(self, dest):
        jpath = 'var/log/journal'
        path = dest / jpath
        if path.exists():
            try:
                shutil.rmtree(path)
            except Exception as e:
                self.error(f'Failed to remove journal dir {jpath}: {e}')
        members = (m for m in self.members if m.get('path').startswith(jpath))
        for m in members:
            self._members.pop(m.get('path'))

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
    def __init__(self, dest, member):
        self._dest = dest
        self._member = member
        d = {'name': self.name, 'path': str(self.path), 'type': self.type}
        if self.type == 'file':
            d['size'] = self.member.size
        if self.type == 'link':
            d['link'] = self.member.linkname
        super().__init__(d)

    @property
    def dest(self):
        return self._dest

    @property
    def member(self):
        return self._member

    @cached_property
    def toplevel(self):
        '''The top-level dir in the member path'''
        return Path(self.member.name).parts[0]

    @cached_property
    def path(self):
        '''The member path, without the top-level dir'''
        return Path(*Path(self.member.name).parts[1:])

    @cached_property
    def full_path(self):
        '''The full, resolved path including the dest path'''
        return self.dest.joinpath(self.member.name).resolve()

    @property
    def name(self):
        return self.path.name

    @property
    def type(self):
        if self.member.isdir():
            return 'dir'
        if self.member.isfile():
            return 'file'
        if self.member.issym() or self.member.islnk():
            return 'link'
        if self.member.ischr():
            return 'chr'
        if self.member.isblk():
            return 'blk'
        if self.member.isfifo():
            return 'fifo'
        return 'unknown'

    @property
    def invalid_path(self):
        return not str(self.full_path).startswith(str(self.dest))

    @property
    def invalid_link(self):
        if self.type != 'link':
            return False
        linkpath = self.full_path.parent.joinpath(self.member.linkname).resolve()
        return not str(linkpath).startswith(str(self.dest))

    def extract_dir(self):
        self.full_path.mkdir(mode=0o775)
        return True

    def extract_file(self, tar):
        toffset = tar.fileobj.tell()
        moffset = self.member.offset_data
        if toffset != moffset:
            LOGGER.warning(f'tar offset {toffset} != member data offset {moffset}')
            tar.fileobj.seek(moffset)
        self.full_path.write_bytes(tar.fileobj.read(self.member.size))
        self.full_path.chmod(self.full_path.stat().st_mode | 0o644)
        return True

    def extract_link(self):
        self.full_path.symlink_to(self.member.linkname)
        return True

    def extract(self, tar):
        if self.type == 'dir':
            return self.extract_dir()
        if self.type == 'file':
            return self.extract_file(tar)
        if self.type == 'link':
            return self.extract_link()
        return False
