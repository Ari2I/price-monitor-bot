"""Тесты для вспомогательных функций bot.handlers."""

import unittest

from bot.handlers import _is_known_difficult_url


class IsKnownDifficultUrlTest(unittest.TestCase):
    def test_detects_wildberries(self):
        self.assertTrue(
            _is_known_difficult_url("https://www.wildberries.ru/catalog/123")
        )

    def test_detects_ozon(self):
        self.assertTrue(
            _is_known_difficult_url("https://www.ozon.ru/product/456")
        )

    def test_detects_yandex_market(self):
        self.assertTrue(
            _is_known_difficult_url("https://market.yandex.ru/product/789")
        )

    def test_detects_lamoda(self):
        self.assertTrue(
            _is_known_difficult_url("https://www.lamoda.ru/p/abc123/")
        )

    def test_regular_shop_is_not_known_difficult(self):
        self.assertFalse(
            _is_known_difficult_url("https://shop.example.com/item/1")
        )


if __name__ == "__main__":
    unittest.main()
