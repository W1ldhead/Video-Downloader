import unittest

from app.links import INSTAGRAM, TIKTOK, X, YOUTUBE, find_links, platform_of


class FindLinksTest(unittest.TestCase):
    def test_single_full_link(self):
        self.assertEqual(
            find_links("https://www.tiktok.com/@cat.lover/video/7301234567890123456"),
            ["https://www.tiktok.com/@cat.lover/video/7301234567890123456"],
        )

    def test_short_links(self):
        text = "смотри https://vm.tiktok.com/ZMabc123/ и ещё vt.tiktok.com/ZSxyz789"
        self.assertEqual(
            find_links(text),
            ["https://vm.tiktok.com/ZMabc123/", "https://vt.tiktok.com/ZSxyz789/"],
        )

    def test_t_link(self):
        self.assertEqual(
            find_links("https://www.tiktok.com/t/ZT8abcDEF/"),
            ["https://www.tiktok.com/t/ZT8abcDEF/"],
        )

    def test_chat_fragment(self):
        text = (
            "Привет! Вот видос (https://www.tiktok.com/@user_1/video/111?is_from_webapp=1&lang=ru), "
            "а это прикол: m.tiktok.com/v/222.html.\n"
            "И вот: «https://vm.tiktok.com/ZMq1w2e3/»!"
        )
        self.assertEqual(
            find_links(text),
            [
                "https://www.tiktok.com/@user_1/video/111",
                "https://m.tiktok.com/v/222.html",
                "https://vm.tiktok.com/ZMq1w2e3/",
            ],
        )

    def test_duplicates_removed(self):
        text = (
            "https://www.tiktok.com/@a/video/555\n"
            "https://www.tiktok.com/@a/video/555?lang=en\n"
            "http://tiktok.com/@a/video/555\n"
            "https://m.tiktok.com/v/555.html\n"
            "https://vm.tiktok.com/ZMcode/ https://vm.tiktok.com/ZMcode"
        )
        self.assertEqual(
            find_links(text),
            ["https://www.tiktok.com/@a/video/555", "https://vm.tiktok.com/ZMcode/"],
        )

    def test_one_per_line_without_spaces(self):
        text = "https://vm.tiktok.com/AAA1/\nhttps://vm.tiktok.com/BBB2/\r\nhttps://vm.tiktok.com/CCC3/"
        self.assertEqual(len(find_links(text)), 3)

    def test_uppercase_host(self):
        self.assertEqual(
            find_links("HTTPS://WWW.TIKTOK.COM/@Bob/video/42"),
            ["https://www.tiktok.com/@Bob/video/42"],
        )

    def test_not_video_ignored(self):
        text = (
            "https://www.tiktok.com/@someone https://www.tiktok.com/ "
            "https://www.tiktok.com/music/song-123 https://youtube.com/watch?v=1 "
            "https://nottiktok.com/@a/video/1 просто текст"
        )
        self.assertEqual(find_links(text), [])

    def test_empty(self):
        self.assertEqual(find_links(""), [])


class OtherPlatformsTest(unittest.TestCase):
    def test_youtube_forms(self):
        text = (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s "
            "https://youtu.be/abcdefghijk?si=xyz "
            "https://m.youtube.com/watch?feature=share&v=ABCDEFGHIJK "
            "https://youtube.com/shorts/Zz9_-Zz9_-Z?feature=share "
            "https://www.youtube.com/live/LiveLiveLiv"
        )
        self.assertEqual(
            find_links(text),
            [
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=abcdefghijk",
                "https://www.youtube.com/watch?v=ABCDEFGHIJK",
                "https://www.youtube.com/shorts/Zz9_-Zz9_-Z",
                "https://www.youtube.com/watch?v=LiveLiveLiv",
            ],
        )

    def test_youtube_duplicates(self):
        text = "https://youtu.be/dQw4w9WgXcQ https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1"
        self.assertEqual(find_links(text), ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])

    def test_youtube_not_video(self):
        text = (
            "https://www.youtube.com/@channel https://www.youtube.com/ "
            "https://www.youtube.com/watch?v=short https://www.youtube.com/playlist?list=PL1"
        )
        self.assertEqual(find_links(text), [])

    def test_instagram(self):
        text = (
            "https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=abc "
            "https://instagram.com/reels/XyZ_123-abc/ "
            "https://www.instagram.com/p/Post123/ "
            "https://www.instagram.com/some.user/reel/UserReel1/ "
            "https://www.instagram.com/reel/C1a2B3c4D5e"
        )
        self.assertEqual(
            find_links(text),
            [
                "https://www.instagram.com/reel/C1a2B3c4D5e/",
                "https://www.instagram.com/reel/XyZ_123-abc/",
                "https://www.instagram.com/p/Post123/",
                "https://www.instagram.com/reel/UserReel1/",
            ],
        )

    def test_instagram_not_video(self):
        self.assertEqual(find_links("https://www.instagram.com/some.user/ https://instagram.com/"), [])

    def test_x(self):
        text = (
            "https://x.com/elonmusk/status/1234567890123456789?s=20 "
            "https://twitter.com/NASA/status/111/video/1 "
            "https://mobile.twitter.com/someone/status/222 "
            "https://x.com/i/status/333 "
            "https://twitter.com/elonmusk/status/1234567890123456789"
        )
        self.assertEqual(
            find_links(text),
            [
                "https://x.com/elonmusk/status/1234567890123456789",
                "https://x.com/NASA/status/111",
                "https://x.com/someone/status/222",
                "https://x.com/i/status/333",
            ],
        )

    def test_x_not_video_and_lookalikes(self):
        text = "https://x.com/elonmusk https://box.com/a/status/1 https://twitter.com/home"
        self.assertEqual(find_links(text), [])

    def test_mixed_and_platform(self):
        text = (
            "тикток https://vm.tiktok.com/ZMabc/ ютуб youtu.be/dQw4w9WgXcQ, "
            "инста instagram.com/reel/AbC/ и икс x.com/a/status/9."
        )
        links = find_links(text)
        self.assertEqual(
            [platform_of(u) for u in links], [TIKTOK, YOUTUBE, INSTAGRAM, X]
        )


if __name__ == "__main__":
    unittest.main()
