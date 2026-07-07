"""
Модели базы данных: отслеживаемые товары и история их цен.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _utcnow() -> datetime:
    """
    Возвращает текущее время в UTC как наивный datetime.

    Наивный формат используется для простоты хранения в SQLite и
    единообразия с остальным кодом проекта (см. reporting.py).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


class Product(Base):
    """Товар, цену которого отслеживает бот."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_chat_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048))
    css_selector: Mapped[str] = mapped_column(String(512))
    force_dynamic: Mapped[bool] = mapped_column(default=False)
    # Количество проверок подряд, при которых не удалось получить
    # цену — используется, чтобы предупредить пользователя о
    # вероятной блокировке сайта, не просто молча повторяя попытки.
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow
    )

    price_records: Mapped[List["PriceRecord"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PriceRecord.checked_at",
    )

    @property
    def latest_price_record(self) -> Optional["PriceRecord"]:
        """Возвращает последнюю по времени запись о цене товара."""
        if not self.price_records:
            return None
        return self.price_records[-1]


class PriceRecord(Base):
    """Одна зафиксированная цена товара в конкретный момент времени."""

    __tablename__ = "price_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, index=True
    )

    product: Mapped["Product"] = relationship(back_populates="price_records")
