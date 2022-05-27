
import logging
import magic
import os
import re
import shutil


LOGGER = logging.getLogger(__name__)


class SOSAnalysisError(Exception):
    pass


class SOSAnalysis(object):
    def __init__(self, sos):
        self.sos = sos
        self.conclusions = []

    def analyse(self):
        self.detect_newlines()
        self.get_conclusions()

    def get_conclusions(self):
        if not self.conclusions:
            for a in self.sos.reductions.analyses:
                LOGGER.debug(f'Getting conclusion for {a.name}: {self.sos.name}')
                try:
                    self.conclusions.append(dict(a.conclusion))
                except Exception:
                    LOGGER.exception(f'Analysis {a.name} failed, skipping')

    def detect_newlines(self):
        if self.sos.linesdir.exists() and not self.sos.dry_run:
            shutil.rmtree(self.sos.linesdir)

        for f in self.sos.file_list.splitlines():
            self.create_newline_file(f)

        for f in self.sos.link_list.splitlines():
            self.create_newline_symlink(f)

    def create_newline_symlink(self, f):
        path = self.sos.file(f)
        lines_path = self.linesdir / f
        lines_path.parent.mkdir(parents=True, exist_ok=True)
        lines_path.symlink_to(os.readlink(str(path)))

    def create_newline_file(self, f):
        path = self.sos.file(f)
        if not magic.from_file(str(path), mime=True).startswith('text'):
            return
        lines_path = self.sos.linesdir / f
        lines_path.parent.mkdir(parents=True, exist_ok=True)
        lines_path.write_text(','.join(map(str, self.newline_iter(path))))

    def newline_iter(self, path):
        return (newline.end() for newline in re.finditer(b'^|\n|(?<!\n)$', path.read_bytes()))
