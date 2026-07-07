"""Тесты для CLI-утилиты check_price."""

import os
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from check_price import main
from parser.tracker import PriceCheckResult


class CheckPriceMainTest(unittest.TestCase):
    @patch("check_price.PriceTracker.get_price")
    def test_returns_zero_and_prints_price_when_found(self, mock_get_price):
        mock_get_price.return_value = PriceCheckResult(
            price=999.0, used_dynamic=False, currency="руб"
        )
        test_args = ["check_price.py", "https://example.com/item"]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout", new_callable=StringIO) as fake_out:
                exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertIn("999.0", fake_out.getvalue())
        self.assertIn("руб", fake_out.getvalue())

    @patch("check_price.PriceTracker.get_price")
    def test_returns_one_and_prints_error_when_not_found(
        self, mock_get_price
    ):
        mock_get_price.return_value = PriceCheckResult(
            price=None,
            used_dynamic=True,
            error="Не удалось определить цену",
        )
        test_args = ["check_price.py", "https://example.com/item"]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout", new_callable=StringIO) as fake_out:
                exit_code = main()

        self.assertEqual(exit_code, 1)
        self.assertIn("Не удалось определить цену", fake_out.getvalue())

    @patch("check_price.PriceTracker.get_price")
    def test_passes_selector_and_dynamic_flag_to_tracker(
        self, mock_get_price
    ):
        mock_get_price.return_value = PriceCheckResult(
            price=1.0, used_dynamic=True
        )
        test_args = [
            "check_price.py",
            "https://example.com/item",
            "--selector",
            "span.price",
            "--dynamic",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("sys.stdout", new_callable=StringIO):
                main()

        mock_get_price.assert_called_once_with(
            url="https://example.com/item",
            css_selector="span.price",
            force_dynamic=True,
        )

    @patch("check_price.PriceTracker.get_price")
    @patch("check_price.StaticHtmlFetcher.fetch")
    def test_dump_html_saves_fetched_page_to_file(
        self, mock_fetch, mock_get_price
    ):
        mock_fetch.return_value = "<html>тестовая страница</html>"
        mock_get_price.return_value = PriceCheckResult(
            price=None, used_dynamic=False, error="не найдено"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "page.html")
            test_args = [
                "check_price.py",
                "https://example.com/item",
                "--dump-html",
                output_path,
            ]
            with patch.object(sys, "argv", test_args):
                with patch("sys.stdout", new_callable=StringIO) as fake_out:
                    main()

            self.assertTrue(os.path.exists(output_path))
            with open(output_path, "r", encoding="utf-8") as html_file:
                content = html_file.read()
            self.assertEqual(content, "<html>тестовая страница</html>")
            self.assertIn("HTML сохранён в файл", fake_out.getvalue())

    @patch("check_price.StaticHtmlFetcher.fetch")
    def test_dump_html_reports_fetch_error(self, mock_fetch):
        from parser.base import HtmlFetchError

        mock_fetch.side_effect = HtmlFetchError("нет соединения")

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = os.path.join(tmp_dir, "page.html")
            test_args = [
                "check_price.py",
                "https://example.com/item",
                "--dump-html",
                output_path,
            ]
            with patch("check_price.PriceTracker.get_price") as mock_get:
                mock_get.return_value = PriceCheckResult(
                    price=None, used_dynamic=False, error="нет соединения"
                )
                with patch.object(sys, "argv", test_args):
                    with patch(
                        "sys.stdout", new_callable=StringIO
                    ) as fake_out:
                        main()

            self.assertFalse(os.path.exists(output_path))
            self.assertIn(
                "Не удалось получить HTML для сохранения",
                fake_out.getvalue(),
            )


if __name__ == "__main__":
    unittest.main()
