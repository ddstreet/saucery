
import shutil
import tempfile
import unittest

from pathlib import Path
from saucery import Saucery


TEST_DATA_PATH = Path(__file__).parent / 'saucery_data'
TEST_REDUCTIONS_PATH = Path(__file__).parent.parent / 'reductions'
TEST_SOS = 'sosreport-sosreport-f-123456-2022-05-23-qcpndam.tar.xz'


class SauceryTest(unittest.TestCase):
    def setUp(self):
        self.testdir = tempfile.TemporaryDirectory()
        saucery = shutil.copytree(TEST_DATA_PATH, Path(self.testdir.name) / 'saucery')
        self.saucery = Saucery(saucery=saucery, reductions=TEST_REDUCTIONS_PATH)
        self.addCleanup(self.testdir.cleanup)

    def testSauceryContent(self):
        self.assertGreater(len(self.saucery.sosreports), 0)
        sos = self.saucery.sosreports[0]
        self.assertFalse(sos.extracted)
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.analysed)

    def testFull(self):
        sos = self.saucery.sosreport(TEST_SOS)
        self.assertTrue(sos.exists())
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.extracted)
        self.assertFalse(sos.squashed)
        self.assertFalse(sos.mounted)
        self.assertFalse(sos.analysed)

        sos.extract()
        self.assertFalse(sos.invalid)
        self.assertTrue(sos.extracted)
        self.assertFalse(sos.squashed)
        self.assertFalse(sos.mounted)
        self.assertFalse(sos.analysed)
        self.assertGreater(len(sos.files_json), 0)
        self.assertGreater(sos.total_size, 0)
        self.assertEqual(sos.hostname, 'sosreport-f')

        sos.analyse()
        self.assertFalse(sos.invalid)
        self.assertTrue(sos.extracted)
        self.assertFalse(sos.squashed)
        self.assertFalse(sos.mounted)
        self.assertTrue(sos.analysed)
        self.assertEqual(sos.case, '123456')
        sos.analysed = False
        self.assertFalse(sos.analysed)

        sos.squash()
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.extracted)
        self.assertTrue(sos.squashed)
        self.assertFalse(sos.mounted)
        self.assertFalse(sos.analysed)

        self.addCleanup(sos.unmount)
        sos.mount()
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.extracted)
        self.assertTrue(sos.squashed)
        self.assertTrue(sos.mounted)
        self.assertFalse(sos.analysed)

        sos.analyse()
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.extracted)
        self.assertTrue(sos.squashed)
        self.assertTrue(sos.mounted)
        self.assertTrue(sos.analysed)
        self.assertEqual(sos.case, '123456')
