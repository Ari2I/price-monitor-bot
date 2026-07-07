"""
Репозиторий — единая точка доступа к базе данных.

Изолирует остальной код приложения (бота, планировщик) от деталей
работы с SQLAlchemy: обработчики и планировщик вызывают простые
функции, не работая с сессиями и запросами напрямую.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base, PriceRecord, Product


@dataclass
class PriceSnapshot:
    """Цена и валюта последней сохранённой записи по товару."""

    price: float
    currency: Optional[str]


class ProductRepository:
    """Репозиторий для товаров и истории их цен."""

    # Колонки, добавленные в более поздних версиях приложения. Для
    # каждой новой версии базы данных, созданной до появления этой
    # колонки, миграция выполняется автоматически при подключении —
    # в проекте нет системы миграций (Alembic), а такой минимальный
    # ручной ALTER TABLE вполне достаточен для одного-двух полей и
    # работает как в SQLite, так и в PostgreSQL.
    _SCHEMA_MIGRATIONS = [
        ("price_records", "currency", "VARCHAR(8)"),
        ("products", "consecutive_failures", "INTEGER DEFAULT 0"),
    ]

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url)
        Base.metadata.create_all(self._engine)
        self._run_schema_migrations()
        self._session_factory = sessionmaker(bind=self._engine)

    def _run_schema_migrations(self) -> None:
        """Добавляет недостающие колонки в уже существующие таблицы."""
        inspector = inspect(self._engine)
        table_names = set(inspector.get_table_names())

        for table_name, column_name, column_type_sql in self._SCHEMA_MIGRATIONS:
            if table_name not in table_names:
                continue
            columns = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            if column_name in columns:
                continue
            with self._engine.begin() as connection:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {column_type_sql}"
                    )
                )

    def _session(self) -> Session:
        return self._session_factory()

    def add_product(
        self,
        owner_chat_id: int,
        name: str,
        url: str,
        css_selector: str,
        force_dynamic: bool = False,
    ) -> Product:
        """Добавляет новый товар для отслеживания."""
        with self._session() as session:
            product = Product(
                owner_chat_id=owner_chat_id,
                name=name,
                url=url,
                css_selector=css_selector,
                force_dynamic=force_dynamic,
            )
            session.add(product)
            session.commit()
            session.refresh(product)
            return product

    def remove_product(self, owner_chat_id: int, product_id: int) -> bool:
        """Удаляет товар. Возвращает True, если товар был найден."""
        with self._session() as session:
            product = session.get(Product, product_id)
            if product is None or product.owner_chat_id != owner_chat_id:
                return False
            session.delete(product)
            session.commit()
            return True

    def list_products(self, owner_chat_id: int) -> List[Product]:
        """Возвращает список товаров конкретного пользователя."""
        with self._session() as session:
            stmt = select(Product).where(
                Product.owner_chat_id == owner_chat_id
            )
            return list(session.scalars(stmt).all())

    def list_all_owner_chat_ids(self) -> List[int]:
        """Возвращает список ID чатов всех пользователей с товарами."""
        with self._session() as session:
            stmt = select(Product.owner_chat_id).distinct()
            return list(session.scalars(stmt).all())

    def get_product(
        self, owner_chat_id: int, product_id: int
    ) -> Optional[Product]:
        """Возвращает товар пользователя по ID, если он ему принадлежит."""
        with self._session() as session:
            product = session.get(Product, product_id)
            if product is None or product.owner_chat_id != owner_chat_id:
                return None
            session.refresh(product)
            _ = product.price_records  # подгружаем связанные записи
            return product

    def save_price_record(
        self,
        product_id: int,
        price: float,
        currency: Optional[str] = None,
    ) -> PriceRecord:
        """Сохраняет новую запись о цене (и валюте) товара."""
        with self._session() as session:
            record = PriceRecord(
                product_id=product_id, price=price, currency=currency
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_price_history(
        self, product_id: int, limit: int = 30
    ) -> Sequence[PriceRecord]:
        """Возвращает последние записи истории цены товара."""
        with self._session() as session:
            stmt = (
                select(PriceRecord)
                .where(PriceRecord.product_id == product_id)
                .order_by(PriceRecord.checked_at.desc())
                .limit(limit)
            )
            records = list(session.scalars(stmt).all())
            records.reverse()
            return records

    def get_latest_price(self, product_id: int) -> Optional[float]:
        """Возвращает последнюю известную цену товара (без валюты)."""
        history = self.get_price_history(product_id, limit=1)
        return history[0].price if history else None

    def get_latest_price_snapshot(
        self, product_id: int
    ) -> Optional[PriceSnapshot]:
        """Возвращает последнюю известную цену товара вместе с валютой."""
        history = self.get_price_history(product_id, limit=1)
        if not history:
            return None
        record = history[0]
        return PriceSnapshot(price=record.price, currency=record.currency)

    def reset_failure_count(self, product_id: int) -> None:
        """Сбрасывает счётчик подряд идущих неудачных проверок товара."""
        with self._session() as session:
            product = session.get(Product, product_id)
            if product is not None:
                product.consecutive_failures = 0
                session.commit()

    def increment_failure_count(self, product_id: int) -> int:
        """
        Увеличивает счётчик подряд идущих неудачных проверок и
        возвращает новое значение — используется, чтобы предупредить
        пользователя, если сайт систематически не отдаёт цену
        (вероятная блокировка), а не только при разовом сбое.
        """
        with self._session() as session:
            product = session.get(Product, product_id)
            if product is None:
                return 0
            product.consecutive_failures += 1
            session.commit()
            return product.consecutive_failures
