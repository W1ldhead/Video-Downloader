import os
import tempfile
import time
import unittest
from pathlib import Path

from app import cookies
from app.downloader import explain

HEADER = "# Netscape HTTP Cookie File\n"
FUTURE = str(int(time.time()) + 30 * 86400)
PAST = str(int(time.time()) - 86400)


def line(domain: str, name: str, expires: str = FUTURE) -> str:
    return f"{domain}\tTRUE\t/\tTRUE\t{expires}\t{name}\tvalue123\n"


class CookiesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["TIKTOKDL_DATA_DIR"] = self.tmp.name
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        del os.environ["TIKTOKDL_DATA_DIR"]
        self.tmp.cleanup()

    def write(self, text: str) -> Path:
        path = self.dir / "src_cookies.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def test_good_file_installed_as_copy(self):
        src = self.write(HEADER + line(".tiktok.com", "sessionid") + line(".tiktok.com", "tt_csrf"))
        self.assertEqual(cookies.install(src), "")
        self.assertTrue(cookies.is_set())
        self.assertEqual(cookies.stored_path().read_text(encoding="utf-8"), src.read_text(encoding="utf-8"))
        cookies.remove()
        self.assertFalse(cookies.is_set())

    def test_not_netscape(self):
        with self.assertRaises(cookies.CookieError):
            cookies.install(self.write('[{"name": "sessionid"}]'))
        self.assertFalse(cookies.is_set())

    def test_no_tiktok(self):
        with self.assertRaisesRegex(cookies.CookieError, "нет cookies TikTok"):
            cookies.check(self.write(HEADER + line(".youtube.com", "SID")))

    def test_not_logged_in(self):
        with self.assertRaisesRegex(cookies.CookieError, "нет входа"):
            cookies.check(self.write(HEADER + line(".tiktok.com", "tt_csrf")))

    def test_expired_warns(self):
        warning = cookies.check(self.write(HEADER + line(".tiktok.com", "sessionid", PAST)))
        self.assertIn("истёк", warning)

    def test_age_message_depends_on_cookies(self):
        e = Exception("ERROR: [TikTok] 1: This post may not be comfortable for some audiences. Log in for access.")
        self.assertIn("Укажите файл cookies", explain(e))
        cookies.install(self.write(HEADER + line(".tiktok.com", "sessionid")))
        self.assertIn("не принял вход", explain(e))


if __name__ == "__main__":
    unittest.main()
