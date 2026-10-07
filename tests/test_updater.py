import os
import tempfile
import unittest
from pathlib import Path

from app import updater


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["TIKTOKDL_UPDATE_DIR"] = self.tmp.name

    def tearDown(self):
        del os.environ["TIKTOKDL_UPDATE_DIR"]
        self.tmp.cleanup()

    def test_parse_version(self):
        self.assertEqual(updater.parse_version("2026.08.19"), (2026, 8, 19))
        self.assertGreater(updater.parse_version("2026.8.19.1"), updater.parse_version("2026.08.19"))
        self.assertGreater(updater.parse_version("2026.10.1"), updater.parse_version("2026.9.30"))

    def test_no_downloads(self):
        self.assertIsNone(updater.downloaded_wheel())

    def test_newest_wheel_chosen(self):
        folder = Path(self.tmp.name)
        for name in [
            "yt_dlp-2026.8.19-py3-none-any.whl",
            "yt_dlp-2026.10.2-py3-none-any.whl",
            "yt_dlp-2026.9.30-py3-none-any.whl",
            "junk.txt",
            "yt_dlp-2027.1.1-py3-none-any.whl.tmp",
        ]:
            (folder / name).write_bytes(b"")
        version, path = updater.downloaded_wheel()
        self.assertEqual(version, "2026.10.2")
        self.assertEqual(path.name, "yt_dlp-2026.10.2-py3-none-any.whl")


if __name__ == "__main__":
    unittest.main()
