"""Тесты для parser.static_parser."""

import unittest
from unittest.mock import Mock, patch

import requests

from parser.base import HtmlFetchError
from parser.static_parser import StaticHtmlFetcher, extract_price_text

SAMPLE_HTML = """
<html>
  <body>
    <div class="product">
      <h1>Тестовый товар</h1>
      <span class="price">1 299,90 руб.</span>
    </div>
  </body>
</html>
"""


class ExtractPriceTextTest(unittest.TestCase):
    def test_extracts_by_class_selector(self):
        result = extract_price_text(SAMPLE_HTML, "span.price")
        self.assertEqual(result, "1 299,90 руб.")

    def test_returns_none_for_missing_selector(self):
        result = extract_price_text(SAMPLE_HTML, "span.not-existing")
        self.assertIsNone(result)


class StaticHtmlFetcherRetryTest(unittest.TestCase):
    def setUp(self):
        # backoff_seconds=0.01 и мок time.sleep — чтобы тесты не ждали
        # реальные секунды между попытками.
        self.fetcher = StaticHtmlFetcher(max_retries=2, backoff_seconds=0.01)

    @patch("parser.static_parser.time.sleep")
    @patch("parser.static_parser.requests.get")
    def test_succeeds_immediately_without_retry(self, mock_get, mock_sleep):
        mock_response = Mock()
        mock_response.text = "<html>ok</html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.fetcher.fetch("https://example.com")

        self.assertEqual(result, "<html>ok</html>")
        mock_sleep.assert_not_called()
        mock_get.assert_called_once()

    @patch("parser.static_parser.time.sleep")
    @patch("parser.static_parser.requests.get")
    def test_retries_on_timeout_then_succeeds(self, mock_get, mock_sleep):
        success_response = Mock()
        success_response.text = "<html>ok</html>"
        success_response.raise_for_status.return_value = None

        mock_get.side_effect = [
            requests.exceptions.Timeout("timeout"),
            success_response,
        ]

        result = self.fetcher.fetch("https://example.com")

        self.assertEqual(result, "<html>ok</html>")
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("parser.static_parser.time.sleep")
    @patch("parser.static_parser.requests.get")
    def test_raises_after_exhausting_retries(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError(
            "no route"
        )

        with self.assertRaises(HtmlFetchError):
            self.fetcher.fetch("https://example.com")

        # 1 первая попытка + 2 повтора (max_retries=2) = 3 вызова
        self.assertEqual(mock_get.call_count, 3)

    @patch("parser.static_parser.time.sleep")
    @patch("parser.static_parser.requests.get")
    def test_403_is_not_retried(self, mock_get, mock_sleep):
        response = Mock()
        response.status_code = 403
        http_error = requests.exceptions.HTTPError("forbidden")
        http_error.response = response
        response.raise_for_status.side_effect = http_error
        mock_get.return_value = response

        with self.assertRaises(HtmlFetchError) as ctx:
            self.fetcher.fetch("https://example.com")

        self.assertIn("403", str(ctx.exception))
        mock_get.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("parser.static_parser.time.sleep")
    @patch("parser.static_parser.requests.get")
    def test_429_is_retried(self, mock_get, mock_sleep):
        response_429 = Mock()
        response_429.status_code = 429
        http_error = requests.exceptions.HTTPError("too many requests")
        http_error.response = response_429
        response_429.raise_for_status.side_effect = http_error

        success_response = Mock()
        success_response.text = "<html>ok</html>"
        success_response.raise_for_status.return_value = None

        mock_get.side_effect = [response_429, success_response]

        result = self.fetcher.fetch("https://example.com")

        self.assertEqual(result, "<html>ok</html>")
        self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
