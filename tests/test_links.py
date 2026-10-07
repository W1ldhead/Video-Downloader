import unittest

from app.links import find_links


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


if __name__ == "__main__":
    unittest.main()
