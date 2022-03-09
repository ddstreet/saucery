#!/usr/bin/python3

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from contextlib import suppress
from datetime import datetime
from functools import cached_property
from pathlib import Path

try:
    from sftools import SF
except ImportError:
    raise RuntimeError('Please install python3-sftools from https://launchpad.net/~ubuntu-support-team/+archive/ubuntu/sftools')


class Saucery(object):
    SOSREPORT_REGEX = re.compile(r'sosreport-.*\.tar(\.[^.]+)?')

    def __init__(self, path):
        self._path = Path(path)

    @property
    def new(self):
        return self._path / 'new'

    @property
    def sos(self):
        return self._path / 'sos'

    @property
    def dup(self):
        return self._path / 'dup'

    @property
    def bad(self):
        return self._path / 'bad'

    @property
    def jsonfile(self):
        return self._path / 'sauceryreport.json'

    def _sosreports(self, path):
        filenames = [s.name for s in path.iterdir() if s.is_file()]
        return [path / n for n in filenames if self.SOSREPORT_REGEX.match]

    @property
    def sosreports(self):
        return self._sosreports(self.sos)
        
    @property
    def new_sosreports(self):
        return self._sosreports(self.new)

    def process_new(self, filename):
        src = self.new / filename
        if not str(src.resolve()).startswith(str(self.new.resolve())):
            raise ValueError(f'New sosreports must be located under {self.new}: invalid location {src}')

        try:
            SOS.check(src)
        except Exception as e:
            print(f'Error checking {src}: {e}')
            self.bad.mkdir(parents=True, exist_ok=True)
            badfile = src.rename(self.bad / src.name)
            print(f'Moved {src.name} to {badfile}')
            return

        print(f'Found new sosreport: {src.name}')

        dst = self.sos / src.name
        if dst.exists():
            self.dup.mkdir(exist_ok=True)
            dupfile = src.rename(self.dup / src.name)
            print(f'Duplicate {src.name}, moved to {dupfile}')
            return

        print(f'Moving sos {src.name} to {self.sos}')
        self.sos.mkdir(parents=True, exist_ok=True)
        dst = src.rename(dst)
        dst.chmod(0o444)

        self.extract_sos(dst)
        self.process_sos(dst)

    def process_all_new(self):
        for s in self.new_sosreports:
            try:
                self.process_new(s)
            except ValueError as e:
                print(f'ERROR: {e}')

    def sosreport(self, filename):
        src = self.sos / Path(filename)
        if not str(src.resolve()).startswith(str(self.sos.resolve())):
            raise ValueError(f'Sosreports must be located under {self.sos}: invalid location {src}')

        return SOS(src)

    def extract_sos(self, filename, *, reextract=False):
        self.sosreport(filename).extract(reextract=reextract)

    def process_sos(self, filename):
        self.sosreport(filename).process()

    def create_json(self):
        with tempfile.TemporaryDirectory(dir=self.jsonfile.parent) as tmpdir:
            tmpfile = Path(tmpdir) / 'tmpfile'
            tmpfile.write_text(json.dumps([self.sosreport(s).json for s in self.sosreports],
                                          indent=2, sort_keys=True))
            tmpfile.rename(self.jsonfile)


class SOSMetaProperty(property):
    def __init__(self, name):
        self.name = name
        super().__init__(self.read, self.write, self.unlink)

    def metafile(self, sos):
        return sos.workdir / self.name

    def read(self, sos):
        with suppress(FileNotFoundError):
            return self.metafile(sos).read_text().strip()
        return None

    def write(self, sos, value):
        # unlink if no value
        if not value:
            self.unlink(sos)
            return
        if not sos.workdir.is_dir():
            sos.workdir.mkdir(parents=True, exist_ok=False)
            sos.workdir.chmod(0o755)
        self.metafile(sos).write_text(f'{value}\n')

    def unlink(self, sos):
        self.metafile(sos).unlink(missing_ok=True)


class SOS(object):
    # Share the SF instance with all SOS instances
    sf = SF()

    @classmethod
    def check(cls, filename):
        '''Check validity of tar file.

        Raises ValueError if provided filename is not tar file,
        or if any member of the tar file is absolute or contains
        "/../" path elements.
        '''
        print(f'Checking tar file {filename}')
        if not tarfile.is_tarfile(filename):
            raise ValueError(f'sosreport is not tar: {filename}')
        try:
            with tarfile.open(filename) as tar:
                for name in tar.getnames():
                    if name.startswith('/') or name.startswith('..') or '/../' in name:
                        raise ValueError(f'Invalid tar member: {name}')
        except EOFError:
            raise ValueError(f'Invalid/corrupt tarfile')

    def __init__(self, filename):
        self._sosreport = Path(filename).resolve()

        # Require sanely named sosreport
        n = self._sosreport.name
        if not (n.lower().startswith('sosreport-') and
                n.lower().endswith(('.tar', '.tar.xz', '.tar.gz', '.tar.bz2'))):
            raise ValueError(f'Invalid sosreport name {n}')

    @property
    def sosreport(self):
        return self._sosreport

    @cached_property
    def name(self):
        n = self.sosreport.name
        if n.lower().endswith(('.xz', '.gz', '.bz2')):
            n = n.rpartition('.')[0]
        return n.rpartition('.')[0]

    @cached_property
    def workdir(self):
        return self.sosreport.parent / self.name

    # Meta-files; these are all in the workdir
    case = SOSMetaProperty('case')
    customerid = SOSMetaProperty('customerid')
    customername = SOSMetaProperty('customername')
    hotsos = SOSMetaProperty('hotsos.json')

    @property
    def filesdir(self):
        return self.workdir / 'files'

    def file(self, filename, *, command=None):
        d = self.filesdir
        if command:
            d = d / 'sos_commands' / command
        return d / filename

    def _file_read(self, filename, func, *, command=None, strip=True):
        try:
            f = self.file(filename, command=command)
            content = getattr(f, func)()
        except FileNotFoundError:
            return None
        if strip:
            return content.strip()
        return content

    def file_text(self, filename, **kwargs):
        return self._file_read(filename, 'read_text', **kwargs)

    def file_bytes(self, filename, **kwargs):
        return self._file_read(filename, 'read_bytes', **kwargs)

    def extract(self, *, reextract=False):
        if reextract and self.filesdir.exists():
            print(f'Removing existing data at {self.filesdir}')
            shutil.rmtree(self.filesdir)

        if self.filesdir.exists():
            print(f'Already extracted, not re-extracting: {self.filesdir}')
            return

        print(f'Extracting {self.sosreport.name} to {self.filesdir}')
        self.workdir.mkdir(parents=True, exist_ok=False)
        self.workdir.chmod(0o755)
        with tempfile.TemporaryDirectory(dir=self.workdir) as tmpdir:
            with tarfile.open(self.sosreport) as tar:
                for m in tar.getmembers():
                    if m.isdev():
                        continue
                    tar.extract(m, path=tmpdir)
                    if m.issym():
                        continue
                    mode = 0o775 if m.isdir() else 0o664
                    (Path(tmpdir) / m.name).chmod(mode)
            topfiles = list(Path(tmpdir).iterdir())
            if len(topfiles) == 0:
                raise ValueError(f'No files found in sosreport')
            if len(topfiles) > 1:
                raise ValueError(f'sosreport contains multiple top-level directories')
            # Rename the top-level 'sosreport-...' dir so our files/ dir contains the content
            topfiles[0].rename(self.filesdir)

    def process(self):
        print(f'Processing {self.sosreport}')
        self.detect_case()
        self.detect_customer()
        self.gather_hotsos()

    @property
    def _case_from_name(self):
        match = re.search(r'(?<!\d)(?P<case>\d{8})(?!\d)', self.name)
        if match:
            case = self.sf.Case(match.group('case'))
            if case:
                return case.CaseNumber
        return None

    @property
    def _case_from_comments(self):
        cases = self.sf.CaseComment.contains(self.name).case
        if len(cases) == 1:
            return cases[0].CaseNumber
        if len(cases) > 1:
            casenumbers = map(lambda c: c.CaseNumber, cases)
            print(f'Multiple cases matched for {self.name}: {",".join(casenumbers)}')
        return None

    def detect_case(self):
        case = self._case_from_name or self._case_from_comments
        if case:
            self.case = case
            print(f'Detected case number {case} for {self.name}')
        else:
            print(f'Could not detect case number for {self.name}')

    def detect_customer(self):
        if not self.case:
            print(f"Case number not known, can't lookup customer")
            return

        self.customerid = self.sf.Case(self.case).AccountId
        self.customername = self.sf.Account(self.customerid).Name
        print(f'Detected case {self.case} customer Id {self.customerid}: {self.customername}')

    def gather_hotsos(self):
        cmd = ['hotsos']
        cmd += ['--json']
        cmd += ['--all-logs']
        cmd += ['--max-parallel-tasks', str(len(os.sched_getaffinity(0)))]
        cmd += [str(self.filesdir)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, encoding='utf-8')
        self.hotsos = result.stdout

    @property
    def datetime(self):
        if self.isodate:
            return datetime(self.isodate)
        return None

    @cached_property
    def isodate(self):
        cmd = ['date', '--iso-8601=seconds', '--utc']
        for filename in ['date_--utc', 'hwclock', 'date']:
            sosdate = self.file_text(filename, command='date')
            if not sosdate:
                continue
            result = subprocess.run(cmd + [f'--date={sosdate}'],
                                    stdout=subprocess.PIPE, encoding='utf-8')
            if result.returncode == 0:
                return result.stdout.strip()
        return None

    @property
    def hostname(self):
        return self.file_text('hostname')

    @property
    def machineid(self):
        return self.file_text('etc/machine-id')

    @property
    def json(self):
        print(f'Generating JSON for {self.name}')
        return {
            'name': self.name,
            'sosreport': self.sosreport.name,
            'case': self.case,
            'customerid': self.customerid,
            'customername': self.customername,
            'datetime': self.isodate,
            'hostname': self.hostname,
            'machineid': self.machineid,
        }
