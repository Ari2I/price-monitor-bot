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
STATIC_HTML_WITH_JSONLD_PRICE = """
<html><head>
<script type="application/ld+json">
{"@type": "Product", "offers": {"price": "777"}}
</script>
</head><body><div>цены на странице визуально нет</div></body></html>
"""


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

    @patch("parser.tracker.StaticHtmlFetcher.fetch")
    def test_auto_mode_finds_price_via_jsonld(self, mock_static):
        # Пустой селектор ("") включает режим "авто": CSS-селектор
        # не используется вовсе, цена ищется только через JSON-LD.
        mock_static.return_value = STATIC_HTML_WITH_JSONLD_PRICE
        with patch(
            "parser.tracker.DynamicHtmlFetcher.fetch"
        ) as mock_dynamic:
            result = self.tracker.get_price(
                url="https://example.com/item",
                css_selector="",
            )
        self.assertEqual(result.price, 777.0)
        self.assertFalse(result.used_dynamic)
        mock_dynamic.assert_not_called()

    @patch("parser.tracker.StaticHtmlFetcher.fetch")
    def test_jsonld_used_as_fallback_when_selector_not_found(
        self, mock_static
    ):
        # Селектор указан, но не совпадает с реальной вёрсткой —
        # цена всё равно находится через JSON-LD без обращения к
        # Playwright.
        mock_static.return_value = STATIC_HTML_WITH_JSONLD_PRICE
        with patch(
            "parser.tracker.DynamicHtmlFetcher.fetch"
        ) as mock_dynamic:
            result = self.tracker.get_price(
                url="https://example.com/item",
                css_selector="span.not-existing-class",
            )
        self.assertEqual(result.price, 777.0)
        self.assertFalse(result.used_dynamic)
        mock_dynamic.assert_not_called()


if __name__ == "__main__":
    unittest.main()
