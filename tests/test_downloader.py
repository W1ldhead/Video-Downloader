import unittest
from pathlib import Path

from app.downloader import explain, file_path, pick_format, safe_name

# Похоже на реальный ответ yt-dlp для TikTok
FORMATS = [
    {"format_id": "audio", "vcodec": "none", "acodec": "mp3"},
    {"format_id": "download", "format_note": "watermarked", "vcodec": "h264", "acodec": "aac"},
    {"format_id": "h264_low", "vcodec": "h264", "acodec": "aac", "height": 1024, "tbr": 800},
    {"format_id": "h264_high", "vcodec": "h264", "acodec": "aac", "height": 1024, "tbr": 1900},
    {"format_id": "h265", "vcodec": "h265", "acodec": "aac", "height": 1024, "tbr": 2500},
    {"format_id": "bytevc2", "format_note": "UNPLAYABLE", "vcodec": "bytevc2", "acodec": "aac", "height": 2000},
]


class PickFormatTest(unittest.TestCase):
    def test_best_h264_without_watermark(self):
        self.assertEqual(pick_format(FORMATS)["format_id"], "h264_high")

    def test_h265_if_no_h264(self):
        only = [f for f in FORMATS if not f["format_id"].startswith("h264")]
        self.assertEqual(pick_format(only)["format_id"], "h265")

    def test_only_watermarked(self):
        self.assertIsNone(pick_format(FORMATS[:2]))

    def test_empty(self):
        self.assertIsNone(pick_format([]))


class FileNameTest(unittest.TestCase):
    def test_scheme(self):
        self.assertEqual(file_path(Path("C:/x"), "cat.lover", "123"), Path("C:/x/cat.lover_123.mp4"))

    def test_forbidden_chars(self):
        self.assertEqual(safe_name('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_trailing_dots_and_empty(self):
        self.assertEqual(safe_name("name..."), "name")
        self.assertEqual(safe_name("   "), "unknown")


class ExplainTest(unittest.TestCase):
    def test_known(self):
        e = Exception("ERROR: [TikTok] 1: Your IP address is blocked from accessing this post")
        self.assertEqual(explain(e), "Видео недоступно в вашем регионе")

    def test_unknown_is_short(self):
        e = Exception("ERROR: [TikTok] 123: Something odd happened\nTraceback ...")
        self.assertEqual(explain(e), "Something odd happened")


if __name__ == "__main__":
    unittest.main()
