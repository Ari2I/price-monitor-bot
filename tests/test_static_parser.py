"""Тесты для parser.static_parser.extract_price_text."""

import unittest

from parser.static_parser import extract_price_text

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


if __name__ == "__main__":
    unittest.main()
