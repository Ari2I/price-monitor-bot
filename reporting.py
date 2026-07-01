"""
Сервис формирования отчёта по ценам.

Общая логика, используемая как обработчиком команды /report (отчёт
по запросу пользователя), так и планировщиком (отчёт по
расписанию): проверить текущие цены товаров, сохранить их в историю
и подготовить данные для текстового сообщения и/или Excel-файла.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from database.repository import ProductRepository
from export.excel_export import ProductReportRow
from parser.tracker import PriceTracker

logger = logging.getLogger(__name__)


@dataclass
class ProductCheckOutcome:
    """Результат проверки одного товара для отчёта."""

    name: str
    url: str
    current_price: float | None
    previous_price: float | None
    checked_at: datetime | None
    error: str | None


def check_products_for_chat(
    repository: ProductRepository,
    tracker: PriceTracker,
    owner_chat_id: int,
) -> List[ProductCheckOutcome]:
    """
    Проверяет актуальные цены всех товаров пользователя.

    Для каждого товара запрашивается свежая цена, сравнивается с
    последней сохранённой и, если запрос успешен, новая цена
    записывается в историю.
    """
    products = repository.list_products(owner_chat_id)
    outcomes: List[ProductCheckOutcome] = []

    for product in products:
        previous_price = repository.get_latest_price(product.id)
        result = tracker.get_price(
            url=product.url,
            css_selector=product.css_selector,
            force_dynamic=product.force_dynamic,
        )

        if result.price is not None:
            repository.save_price_record(product.id, result.price)
            checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            checked_at = None
            logger.warning(
                "Не удалось получить цену для товара %s (%s): %s",
                product.name,
                product.url,
                result.error,
            )

        outcomes.append(
            ProductCheckOutcome(
                name=product.name,
                url=product.url,
                current_price=result.price,
                previous_price=previous_price,
                checked_at=checked_at,
                error=result.error,
            )
        )

    return outcomes


def build_text_report(outcomes: List[ProductCheckOutcome]) -> str:
    """Формирует текстовый отчёт для отправки в Telegram."""
    if not outcomes:
        return (
            "Список отслеживаемых товаров пуст. Добавьте товар "
            "командой /add"
        )

    lines = ["📊 Отчёт по ценам:\n"]
    for outcome in outcomes:
        if outcome.current_price is None:
            lines.append(f"⚠️ {outcome.name} — не удалось получить цену")
            continue

        line = f"• {outcome.name}: {outcome.current_price:.2f} ₽"
        if outcome.previous_price is not None:
            change = round(outcome.current_price - outcome.previous_price, 2)
            if change > 0:
                line += f" (↑ +{change:.2f})"
            elif change < 0:
                line += f" (↓ {change:.2f})"
            else:
                line += " (без изменений)"
        lines.append(line)

    return "\n".join(lines)


def build_report_rows(
    outcomes: List[ProductCheckOutcome],
) -> List[ProductReportRow]:
    """Преобразует результаты проверки в строки для Excel-отчёта."""
    return [
        ProductReportRow(
            name=outcome.name,
            url=outcome.url,
            current_price=outcome.current_price,
            previous_price=outcome.previous_price,
            checked_at=outcome.checked_at,
        )
        for outcome in outcomes
    ]
