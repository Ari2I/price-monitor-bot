"""Тесты для parser.price_utils.parse_price и extract_currency_symbol."""

import unittest

from parser.price_utils import extract_currency_symbol, parse_price


class ParsePriceTest(unittest.TestCase):
    def test_simple_integer(self):
        self.assertEqual(parse_price("49999"), 49999.0)

    def test_with_thousand_space_and_comma_decimal(self):
        self.assertEqual(parse_price("1 299,90 руб."), 1299.90)

    def test_with_nbsp_thousand_separator(self):
        self.assertEqual(parse_price("1\u00A0299\u00A0руб."), 1299.0)

    def test_with_dot_thousand_and_comma_decimal(self):
        self.assertEqual(parse_price("1.299,90 ₽"), 1299.90)

    def test_with_dollar_sign_and_dot_decimal(self):
        self.assertEqual(parse_price("$49.99"), 49.99)

    def test_comma_as_thousand_separator(self):
        # Три цифры после запятой -> это разделитель тысяч, не десятичный
        self.assertEqual(parse_price("12,500 руб."), 12500.0)

    def test_none_input(self):
        self.assertIsNone(parse_price(None))

    def test_empty_string(self):
        self.assertIsNone(parse_price(""))

    def test_no_digits(self):
        self.assertIsNone(parse_price("Цена по запросу"))


class ExtractCurrencySymbolTest(unittest.TestCase):
    def test_ruble_abbreviation(self):
        self.assertEqual(extract_currency_symbol("1 299,90 руб."), "руб")

    def test_ruble_sign(self):
        self.assertEqual(extract_currency_symbol("1.299,90 ₽"), "₽")

    def test_dollar_sign_before_number(self):
        self.assertEqual(extract_currency_symbol("$49.99"), "$")

    def test_euro_sign_before_number(self):
        self.assertEqual(extract_currency_symbol("€49.99"), "€")

    def test_currency_code_after_number(self):
        self.assertEqual(extract_currency_symbol("49.99 USD"), "USD")

    def test_no_currency_found_for_plain_number(self):
        self.assertIsNone(extract_currency_symbol("49999"))

    def test_none_input(self):
        self.assertIsNone(extract_currency_symbol(None))

    def test_empty_string(self):
        self.assertIsNone(extract_currency_symbol(""))


if __name__ == "__main__":
    unittest.main()
