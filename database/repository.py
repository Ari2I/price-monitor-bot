"""
Репозиторий — единая точка доступа к базе данных.

Изолирует остальной код приложения (бота, планировщик) от деталей
работы с SQLAlchemy: обработчики и планировщик вызывают простые
функции, не работая с сессиями и запросами напрямую.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base, PriceRecord, Product


class ProductRepository:
    """Репозиторий для товаров и истории их цен."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url)
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)

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

    def save_price_record(self, product_id: int, price: float) -> PriceRecord:
        """Сохраняет новую запись о цене товара."""
        with self._session() as session:
            record = PriceRecord(product_id=product_id, price=price)
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
        """Возвращает последнюю известную цену товара."""
        history = self.get_price_history(product_id, limit=1)
        return history[0].price if history else None
