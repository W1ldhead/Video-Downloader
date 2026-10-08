import unittest
from pathlib import Path

from app.downloader import _resolve, explain, file_path, pick_format, safe_name

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


class PickFormatXTest(unittest.TestCase):
    # Как у X: у цельных mp4 кодеки не подписаны, у потоков HLS картинка и звук отдельно
    X_FORMATS = [
        {"format_id": "hls-audio-128000", "protocol": "m3u8_native", "vcodec": "none", "acodec": None},
        {"format_id": "hls-716", "protocol": "m3u8_native", "vcodec": "avc1.64001F", "acodec": "none", "height": 720},
        {"format_id": "http-288", "protocol": "https", "height": 270, "tbr": 288},
        {"format_id": "http-2176", "protocol": "https", "height": 720, "tbr": 2176},
        {"format_id": "http-832", "protocol": "https", "height": 360, "tbr": 832},
    ]

    def test_best_progressive_mp4(self):
        self.assertEqual(pick_format(self.X_FORMATS, "X")["format_id"], "http-2176")

    def test_only_split_streams(self):
        self.assertIsNone(pick_format(self.X_FORMATS[:2], "X"))

    def test_silent_video(self):
        # Немой ролик Instagram: звука нет нигде — берём картинку
        silent = [
            {"format_id": "a", "vcodec": None, "acodec": "none", "height": 640},
            {"format_id": "dash-v", "vcodec": "avc1", "acodec": "none", "height": 640, "tbr": 900},
        ]
        self.assertIsNotNone(pick_format(silent, "Instagram"))
        # А если звук где-то есть — немую картинку одну не берём (её надо склеить)
        with_audio = silent + [{"format_id": "dash-a", "vcodec": "none", "acodec": "mp4a"}]
        self.assertIsNone(pick_format(with_audio, "Instagram"))

    def test_watermark_only_for_tiktok(self):
        wm = [{"format_id": "a", "format_note": "watermarked", "vcodec": "h264", "acodec": "aac"}]
        self.assertIsNone(pick_format(wm, "TikTok"))
        self.assertEqual(pick_format(wm, "X")["format_id"], "a")


class YoutubePickTest(unittest.TestCase):
    # Похоже на YouTube: раздельные картинка и звук + один цельный 360p
    F = [
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "abr": 160},
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "height": 360, "tbr": 500},
        {"format_id": "134", "vcodec": "avc1.4d401e", "acodec": "none", "height": 360, "tbr": 300},
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none", "height": 720, "tbr": 1500},
        {"format_id": "247", "vcodec": "vp9", "acodec": "none", "height": 720, "tbr": 1600},
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080, "tbr": 4000},
        {"format_id": "248", "vcodec": "vp9", "acodec": "none", "height": 1080, "tbr": 2600},
        {"format_id": "271", "vcodec": "vp9", "acodec": "none", "height": 1440, "tbr": 9000},
        {"format_id": "401", "vcodec": "av01.0.12M.08", "acodec": "none", "height": 2160, "tbr": 18000},
        {"format_id": "313", "vcodec": "vp9", "acodec": "none", "height": 2160, "tbr": 20000},
        {"format_id": "hls-1080", "vcodec": "avc1", "acodec": "none", "height": 1080, "tbr": 9999,
         "protocol": "m3u8_native"},
    ]

    def pick(self, quality):
        from app.downloader import youtube_pick

        return youtube_pick(self.F, quality)

    def test_1080_prefers_h264_and_aac(self):
        self.assertEqual(self.pick(1080), ("137", "140"))

    def test_720(self):
        self.assertEqual(self.pick(720), ("136", "140"))

    def test_1440_takes_best_codec(self):
        self.assertEqual(self.pick(1440), ("271", "140"))

    def test_max_and_4k(self):
        self.assertEqual(self.pick(0), ("313", "140"))
        self.assertEqual(self.pick(2160), ("313", "140"))

    def test_360_prefers_video_only_plus_best_audio(self):
        self.assertEqual(self.pick(360), ("134", "140"))

    def test_lower_than_everything_takes_smallest(self):
        self.assertEqual(self.pick(240), ("134", "140"))

    def test_missing_height_takes_next_lower(self):
        only = [f for f in self.F if f.get("height") != 1080]
        from app.downloader import youtube_pick

        self.assertEqual(youtube_pick(only, 1080), ("136", "140"))

    def test_no_video(self):
        from app.downloader import youtube_pick

        self.assertIsNone(youtube_pick(self.F[:2], 1080))


class ResolveTest(unittest.TestCase):
    """Короткая ссылка приходит как «ссылка на ссылку» — надо дойти до видео."""

    class FakeYdl:
        def __init__(self, pages):
            self.pages = pages

        def extract_info(self, url, download, process, ie_key=None):
            return self.pages[url]

    def test_follows_redirects(self):
        video = {"id": "123", "uploader": "cat", "formats": []}
        ydl = self.FakeYdl({"https://full/1": {"_type": "url", "url": "https://full/2"}, "https://full/2": video})
        start = {"_type": "url", "url": "https://full/1"}
        self.assertEqual(_resolve(ydl, start), video)

    def test_transparent_keeps_wrapper_fields(self):
        ydl = self.FakeYdl({"https://v": {"id": "1", "uploader": "a", "title": None}})
        start = {"_type": "url_transparent", "url": "https://v", "title": "Заголовок"}
        result = _resolve(ydl, start)
        self.assertEqual((result["id"], result["uploader"], result["title"]), ("1", "a", "Заголовок"))

    def test_plain_video_untouched(self):
        video = {"id": "1"}
        self.assertIs(_resolve(self.FakeYdl({}), video), video)


class FileNameTest(unittest.TestCase):
    def test_numbered(self):
        self.assertEqual(file_path(Path("C:/x"), "NASA", "111", 2), Path("C:/x/NASA_111_2.mp4"))

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

    def test_colored_age_restricted(self):
        e = Exception(
            "\x1b[0;31mERROR:\x1b[0m [TikTok] 7633872015992065287: This post may not be comfortable "
            "for some audiences. Log in for access. Use --cookies-from-browser or --cookies"
        )
        self.assertIn("Видео 18+", explain(e))

    def test_colored_unknown(self):
        e = Exception("\x1b[0;31mERROR:\x1b[0m [TikTok] 1: Strange thing")
        self.assertEqual(explain(e), "Strange thing")

    def test_x_errors(self):
        cases = {
            "ERROR: [twitter] 1: NSFW tweet requires authentication. Use --cookies": "деликатным",
            "ERROR: [twitter] 1: You are not authorized to view this protected tweet": "Аккаунт закрыт",
            "ERROR: [twitter] 1: No video could be found in this tweet": "нет видео",
            "ERROR: [twitter] 1: Requested tweet is unavailable": "удалён",
        }
        for text, expected in cases.items():
            self.assertIn(expected, explain(Exception(text)), text)

    def test_instagram_errors(self):
        cases = {
            "ERROR: [Instagram] X: This content is only available for registered users who follow this account": "Закрытый аккаунт",
            "ERROR: [Instagram] X: The webpage request was redirected to the login page. You have exceeded the rate-limit": "временно ограничил",
            "ERROR: [Instagram] X: Restricted Video: You must be 18 years old": "ограничением",
            "ERROR: [Instagram] X: Instagram sent an empty media response. Check if this post": "без входа",
        }
        for text, expected in cases.items():
            self.assertIn(expected, explain(Exception(text)), text)

    def test_unknown_is_short(self):
        e = Exception("ERROR: [TikTok] 123: Something odd happened\nTraceback ...")
        self.assertEqual(explain(e), "Something odd happened")


if __name__ == "__main__":
    unittest.main()
