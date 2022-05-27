
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

    def tearDown(self):
        self.testdir.cleanup()

    def testSauceryContent(self):
        self.assertGreater(len(self.saucery.sosreports), 0)
        sos = self.saucery.sosreports[0]
        self.assertFalse(sos.extracted)
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.analysed)

    def testExtractAnalyse(self):
        sos = self.saucery.sosreport(TEST_SOS)
        self.assertTrue(sos.exists())
        self.assertFalse(sos.extracted)

        sos.extract()
        self.assertTrue(sos.extracted)
        self.assertFalse(sos.invalid)
        self.assertFalse(sos.analysed)
        self.assertGreater(sos.file_count, 0)
        self.assertIsNotNone(sos.file_list)
        self.assertEqual(sos.hostname, 'sosreport-f')

        sos.analyse()
        self.assertEqual(sos.case, '123456')
