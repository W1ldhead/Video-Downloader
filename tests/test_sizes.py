import unittest

from app.sizes import estimate_text, human


class SizesTest(unittest.TestCase):
    def test_human(self):
        self.assertEqual(human(512), "512 Б")
        self.assertEqual(human(850 * 1024), "850 КБ")
        self.assertEqual(human(int(45.6 * 1024 ** 2)), "45,6 МБ")
        self.assertEqual(human(int(1.3 * 1024 ** 3)), "1,3 ГБ")
        self.assertEqual(human(None), "?")

    def test_estimate_text(self):
        self.assertEqual(estimate_text(int(45.6 * 1024 ** 2), True), "45,6 МБ")
        self.assertEqual(estimate_text(int(45.6 * 1024 ** 2), False), "≈ 45,6 МБ")
        self.assertEqual(estimate_text(None, False), "размер неизвестен")


if __name__ == "__main__":
    unittest.main()
