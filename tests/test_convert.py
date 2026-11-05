import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


with patch("site.addsitedir"), patch.dict(sys.modules, {"win32file": SimpleNamespace(
        ReplaceFile=lambda destination, replacement, backup: os.replace(replacement, destination))}):
    from text_convert import convert


class TextConversionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("nkf"), "nkf is not on PATH")
    def test_conversion_replaces_original_and_preserves_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_bytes(b"one\r\ntwo\r\n")
            before = path.stat().st_mtime_ns
            self.assertTrue(convert.convert(str(path), "utf-8", "lf", shutil.which("nkf")))
            self.assertEqual(path.read_bytes(), b"one\ntwo\n")
            self.assertEqual(path.stat().st_mtime_ns, before)
            self.assertEqual(list(Path(directory).iterdir()), [path])
