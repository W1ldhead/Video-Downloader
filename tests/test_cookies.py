import os
import tempfile
import time
import unittest
from pathlib import Path

from app import cookies
from app.downloader import explain
from app.links import INSTAGRAM, TIKTOK, X, YOUTUBE

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

    def write(self, text: str, name: str = "src_cookies.txt") -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_good_file_installed_as_copy(self):
        src = self.write(HEADER + line(".tiktok.com", "sessionid") + line(".tiktok.com", "tt_csrf"))
        self.assertEqual(cookies.install(src, TIKTOK), "")
        self.assertTrue(cookies.is_set(TIKTOK))
        self.assertFalse(cookies.is_set(INSTAGRAM))
        self.assertEqual(cookies.stored_path(TIKTOK).read_text(encoding="utf-8"), src.read_text(encoding="utf-8"))
        cookies.remove(TIKTOK)
        self.assertFalse(cookies.is_set(TIKTOK))

    def test_login_cookie_per_platform(self):
        good = {
            TIKTOK: line(".tiktok.com", "sessionid"),
            INSTAGRAM: line(".instagram.com", "sessionid"),
            X: line(".x.com", "auth_token"),
            YOUTUBE: line(".youtube.com", "LOGIN_INFO"),
        }
        for platform, text in good.items():
            self.assertEqual(cookies.check(self.write(HEADER + text), platform), "", platform)
        # Старый домен X тоже подходит
        self.assertEqual(cookies.check(self.write(HEADER + line(".twitter.com", "auth_token")), X), "")

    def test_wrong_site(self):
        # Файл TikTok указали для Instagram
        with self.assertRaisesRegex(cookies.CookieError, "нет cookies Instagram"):
            cookies.check(self.write(HEADER + line(".tiktok.com", "sessionid")), INSTAGRAM)
        # Похожий, но чужой домен
        with self.assertRaisesRegex(cookies.CookieError, "нет cookies X"):
            cookies.check(self.write(HEADER + line(".box.com", "auth_token")), X)

    def test_not_netscape(self):
        with self.assertRaises(cookies.CookieError):
            cookies.install(self.write('[{"name": "sessionid"}]'), TIKTOK)
        self.assertFalse(cookies.is_set(TIKTOK))

    def test_not_logged_in(self):
        with self.assertRaisesRegex(cookies.CookieError, "нет входа"):
            cookies.check(self.write(HEADER + line(".tiktok.com", "tt_csrf")), TIKTOK)

    def test_expired_warns(self):
        warning = cookies.check(self.write(HEADER + line(".tiktok.com", "sessionid", PAST)), TIKTOK)
        self.assertIn("истёк", warning)

    def test_old_single_file_migrates_to_tiktok(self):
        old = self.dir / "cookies.txt"
        old.write_text(HEADER + line(".tiktok.com", "sessionid"), encoding="utf-8")
        self.assertTrue(cookies.is_set(TIKTOK))
        self.assertFalse(old.exists())
        self.assertFalse(cookies.is_set(X))

    def test_login_hint_depends_on_platform_cookies(self):
        e = Exception("ERROR: [TikTok] 1: This post may not be comfortable for some audiences. Log in for access.")
        self.assertIn("меню «Аккаунты»", explain(e, TIKTOK))
        cookies.install(self.write(HEADER + line(".tiktok.com", "sessionid")), TIKTOK)
        self.assertIn("не подошёл", explain(e, TIKTOK))
        # Вход TikTok не считается входом X
        x_error = Exception("ERROR: [twitter] 1: NSFW tweet requires authentication. Use --cookies")
        self.assertIn("меню «Аккаунты»", explain(x_error, X))


if __name__ == "__main__":
    unittest.main()
