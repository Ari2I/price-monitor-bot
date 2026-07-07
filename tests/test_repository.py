"""Тесты для database.repository.ProductRepository."""

import os
import sqlite3
import tempfile
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

    def test_price_snapshot_includes_currency(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        self.assertIsNone(
            self.repository.get_latest_price_snapshot(product.id)
        )

        self.repository.save_price_record(product.id, 100.0, "RUB")
        self.repository.save_price_record(product.id, 110.0, "RUB")

        snapshot = self.repository.get_latest_price_snapshot(product.id)
        self.assertEqual(snapshot.price, 110.0)
        self.assertEqual(snapshot.currency, "RUB")

    def test_price_snapshot_currency_can_be_none(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        self.repository.save_price_record(product.id, 100.0)

        snapshot = self.repository.get_latest_price_snapshot(product.id)
        self.assertEqual(snapshot.price, 100.0)
        self.assertIsNone(snapshot.currency)

    def test_list_all_owner_chat_ids(self):
        self.repository.add_product(1, "A", "https://a", ".price")
        self.repository.add_product(2, "B", "https://b", ".price")
        self.repository.add_product(2, "C", "https://c", ".price")

        owner_ids = set(self.repository.list_all_owner_chat_ids())
        self.assertEqual(owner_ids, {1, 2})

    def test_new_product_has_zero_consecutive_failures(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        self.assertEqual(product.consecutive_failures, 0)

    def test_increment_failure_count_accumulates(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        self.assertEqual(self.repository.increment_failure_count(product.id), 1)
        self.assertEqual(self.repository.increment_failure_count(product.id), 2)
        self.assertEqual(self.repository.increment_failure_count(product.id), 3)

    def test_reset_failure_count_sets_back_to_zero(self):
        product = self.repository.add_product(
            1, "Товар", "https://x", ".price"
        )
        self.repository.increment_failure_count(product.id)
        self.repository.increment_failure_count(product.id)

        self.repository.reset_failure_count(product.id)

        refreshed = self.repository.get_product(1, product.id)
        self.assertEqual(refreshed.consecutive_failures, 0)

    def test_increment_failure_count_for_missing_product_returns_zero(self):
        result = self.repository.increment_failure_count(999999)
        self.assertEqual(result, 0)

    def test_migrates_legacy_database_missing_new_columns(self):
        """
        Открытие базы, созданной старой версией приложения (до
        появления поддержки валют и счётчика сбоев, без колонок
        currency и consecutive_failures), не должно падать —
        репозиторий сам добавляет обе недостающие колонки.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "legacy.db")
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE products (
                    id INTEGER PRIMARY KEY,
                    owner_chat_id INTEGER,
                    name VARCHAR(255),
                    url VARCHAR(2048),
                    css_selector VARCHAR(512),
                    force_dynamic BOOLEAN,
                    created_at DATETIME
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE price_records (
                    id INTEGER PRIMARY KEY,
                    product_id INTEGER,
                    price FLOAT,
                    checked_at DATETIME
                )
                """
            )
            connection.execute(
                "INSERT INTO products (id, owner_chat_id, name, url, "
                "css_selector, force_dynamic, created_at) VALUES "
                "(1, 1, 'Старый товар', 'https://x', '.price', 0, "
                "'2026-01-01 00:00:00')"
            )
            connection.execute(
                "INSERT INTO price_records "
                "(id, product_id, price, checked_at) VALUES "
                "(1, 1, 100.0, '2026-01-01 00:00:00')"
            )
            connection.commit()
            connection.close()

            repository = ProductRepository(f"sqlite:///{db_path}")
            snapshot = repository.get_latest_price_snapshot(1)

            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.price, 100.0)
            self.assertIsNone(snapshot.currency)

            # Колонка consecutive_failures тоже должна быть добавлена
            # и по умолчанию равна 0 для уже существующих строк.
            product = repository.get_product(1, 1)
            self.assertEqual(product.consecutive_failures, 0)
            self.assertEqual(repository.increment_failure_count(1), 1)

            # После миграции в базу уже можно писать записи с валютой.
            repository.save_price_record(1, 110.0, "USD")
            updated_snapshot = repository.get_latest_price_snapshot(1)
            self.assertEqual(updated_snapshot.currency, "USD")


if __name__ == "__main__":
    unittest.main()
