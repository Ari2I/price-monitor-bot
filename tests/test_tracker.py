"""
Тесты для parser.tracker.PriceTracker.

Сетевые вызовы (HTTP и Playwright) подменяются моками, чтобы тесты
были быстрыми и не зависели от доступности интернета.
"""

import unittest
from unittest.mock import patch

from parser.base import HtmlFetchError
from parser.tracker import PriceTracker

STATIC_HTML_WITH_PRICE = '<span class="price">999 руб.</span>'
STATIC_HTML_WITHOUT_PRICE = "<div>цена не найдена в статике</div>"
DYNAMIC_HTML_WITH_PRICE = '<span class="price">1999 руб.</span>'


class PriceTrackerTest(unittest.TestCase):
    def setUp(self):
        self.tracker = PriceTracker()

    @patch("parser.tracker.StaticHtmlFetcher.fetch")
    def test_static_fetch_success_does_not_use_dynamic(self, mock_static):
        mock_static.return_value = STATIC_HTML_WITH_PRICE
        with patch(
            "parser.tracker.DynamicHtmlFetcher.fetch"
        ) as mock_dynamic:
            result = self.tracker.get_price(
                url="https://example.com/item",
                css_selector="span.price",
            )
        self.assertEqual(result.price, 999.0)
        self.assertFalse(result.used_dynamic)
        mock_dynamic.assert_not_called()

    @patch("parser.tracker.DynamicHtmlFetcher.fetch")
    @patch("parser.tracker.StaticHtmlFetcher.fetch")
    def test_falls_back_to_dynamic_when_static_selector_missing(
        self, mock_static, mock_dynamic
    ):
        mock_static.return_value = STATIC_HTML_WITHOUT_PRICE
        mock_dynamic.return_value = DYNAMIC_HTML_WITH_PRICE

        result = self.tracker.get_price(
            url="https://example.com/item",
            css_selector="span.price",
        )
        self.assertEqual(result.price, 1999.0)
        self.assertTrue(result.used_dynamic)

    @patch("parser.tracker.DynamicHtmlFetcher.fetch")
    def test_force_dynamic_skips_static_fetch(self, mock_dynamic):
        mock_dynamic.return_value = DYNAMIC_HTML_WITH_PRICE
        with patch(
            "parser.tracker.StaticHtmlFetcher.fetch"
        ) as mock_static:
            result = self.tracker.get_price(
                url="https://example.com/item",
                css_selector="span.price",
                force_dynamic=True,
            )
        self.assertEqual(result.price, 1999.0)
        mock_static.assert_not_called()

    @patch("parser.tracker.DynamicHtmlFetcher.fetch")
    @patch("parser.tracker.StaticHtmlFetcher.fetch")
    def test_returns_error_when_both_methods_fail(
        self, mock_static, mock_dynamic
    ):
        mock_static.side_effect = HtmlFetchError("нет соединения")
        mock_dynamic.side_effect = HtmlFetchError("браузер не запустился")

        result = self.tracker.get_price(
            url="https://example.com/item",
            css_selector="span.price",
        )
        self.assertIsNone(result.price)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
