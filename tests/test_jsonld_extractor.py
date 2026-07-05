"""Тесты для parser.jsonld_extractor.extract_price_from_jsonld."""

import unittest

from parser.jsonld_extractor import extract_price_from_jsonld

HTML_WITH_OFFER_PRICE = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Тестовый товар",
  "offers": {
    "@type": "Offer",
    "price": "1299.90",
    "priceCurrency": "RUB"
  }
}
</script>
</head><body></body></html>
"""

HTML_WITH_GRAPH_AND_NUMERIC_PRICE = """
<html><head>
<script type="application/ld+json">
{
  "@graph": [
    {"@type": "WebPage", "name": "Страница товара"},
    {
      "@type": "Product",
      "offers": {"@type": "AggregateOffer", "lowPrice": 999, "highPrice": 1499}
    }
  ]
}
</script>
</head><body></body></html>
"""

HTML_WITHOUT_JSONLD = "<html><body><div>Просто страница</div></body></html>"

HTML_WITH_MALFORMED_JSONLD = """
<html><head>
<script type="application/ld+json">
{ "это": "не корректный JSON",
</script>
</head><body></body></html>
"""

HTML_WITH_MULTIPLE_SCRIPTS = """
<html><head>
<script type="application/ld+json">
{"@type": "BreadcrumbList", "itemListElement": []}
</script>
<script type="application/ld+json">
{"@type": "Product", "offers": {"price": "499"}}
</script>
</head><body></body></html>
"""


class ExtractPriceFromJsonldTest(unittest.TestCase):
    def test_extracts_price_from_offer(self):
        result = extract_price_from_jsonld(HTML_WITH_OFFER_PRICE)
        self.assertEqual(result, 1299.90)

    def test_extracts_numeric_low_price_inside_graph(self):
        result = extract_price_from_jsonld(HTML_WITH_GRAPH_AND_NUMERIC_PRICE)
        self.assertEqual(result, 999.0)

    def test_returns_none_without_jsonld(self):
        result = extract_price_from_jsonld(HTML_WITHOUT_JSONLD)
        self.assertIsNone(result)

    def test_returns_none_for_malformed_jsonld(self):
        result = extract_price_from_jsonld(HTML_WITH_MALFORMED_JSONLD)
        self.assertIsNone(result)

    def test_checks_all_script_blocks_until_price_found(self):
        result = extract_price_from_jsonld(HTML_WITH_MULTIPLE_SCRIPTS)
        self.assertEqual(result, 499.0)


if __name__ == "__main__":
    unittest.main()
