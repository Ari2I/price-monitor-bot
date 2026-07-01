"""Тесты для database.repository.ProductRepository."""

import unittest

from database.repository import ProductRepository


class ProductRepositoryTest(unittest.TestCase):
    def setUp(self):
        # Отдельная in-memory база для каждого теста через файловый
        # SQLite не подходит (каждое подключение — новая БД в памяти),
        # поэтому используем общий движок через query-параметр.
        self.repository = ProductRepository("sqlite:///:memory:")

    def test_add_and_list_products(self):
        self.repository.add_product(
            owner_chat_id=1,
            name="Ноутбук X",
            url="https://example.com/laptop",
            css_selector=".price",
        )
        products = self.repository.list_products(owner_chat_id=1)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "Ноутбук X")

    def test_list_products_isolated_by_owner(self):
        self.repository.add_product(1, "Товар A", "https://a", ".price")
        self.repository.add_product(2, "Товар B", "https://b", ".price")

        self.assertEqual(len(self.repository.list_products(1)), 1)
        self.assertEqual(len(self.repository.list_products(2)), 1)

    def test_remove_product_only_by_owner(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        # Чужой пользователь не может удалить товар
        self.assertFalse(self.repository.remove_product(2, product.id))
        # Владелец может
        self.assertTrue(self.repository.remove_product(1, product.id))
        self.assertEqual(self.repository.list_products(1), [])

    def test_price_history_and_latest_price(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        self.assertIsNone(self.repository.get_latest_price(product.id))

        self.repository.save_price_record(product.id, 100.0)
        self.repository.save_price_record(product.id, 110.0)

        self.assertEqual(self.repository.get_latest_price(product.id), 110.0)
        history = self.repository.get_price_history(product.id)
        self.assertEqual([r.price for r in history], [100.0, 110.0])

    def test_list_all_owner_chat_ids(self):
        self.repository.add_product(1, "A", "https://a", ".price")
        self.repository.add_product(2, "B", "https://b", ".price")
        self.repository.add_product(2, "C", "https://c", ".price")

        owner_ids = set(self.repository.list_all_owner_chat_ids())
        self.assertEqual(owner_ids, {1, 2})


if __name__ == "__main__":
    unittest.main()
