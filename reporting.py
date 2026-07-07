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

# Валюта по умолчанию для отображения, если её не удалось определить
# ни через JSON-LD (priceCurrency), ни по символу рядом с ценой.
# Используется как отображаемое значение, а не как факт о товаре —
# для большинства отслеживаемых магазинов это разумное предположение,
# но именно предположение, а не гарантированно верное значение.
DEFAULT_CURRENCY_LABEL = "₽"

# Начиная с этого количества проверок подряд без успеха, в отчёте
# показывается отдельное предупреждение о вероятной блокировке —
# разовый сбой (например, сайт был недоступен секунду) ещё ни о чём
# не говорит, а систематические неудачи уже стоит показать явно, а
# не просто повторять попытки молча.
CONSECUTIVE_FAILURES_WARNING_THRESHOLD = 3


@dataclass
class ProductCheckOutcome:
    """Результат проверки одного товара для отчёта."""

    name: str
    url: str
    current_price: float | None
    current_currency: str | None
    previous_price: float | None
    previous_currency: str | None
    checked_at: datetime | None
    error: str | None
    consecutive_failures: int


def check_products_for_chat(
    repository: ProductRepository,
    tracker: PriceTracker,
    owner_chat_id: int,
) -> List[ProductCheckOutcome]:
    """
    Проверяет актуальные цены всех товаров пользователя.

    Для каждого товара запрашивается свежая цена и валюта,
    сравнивается с последней сохранённой и, если запрос успешен,
    новая цена записывается в историю, а счётчик подряд идущих
    сбоев сбрасывается. При неудаче счётчик увеличивается — это
    позволяет отличить разовый сбой от систематической блокировки.
    """
    products = repository.list_products(owner_chat_id)
    outcomes: List[ProductCheckOutcome] = []

    for product in products:
        previous_snapshot = repository.get_latest_price_snapshot(product.id)
        previous_price = (
            previous_snapshot.price if previous_snapshot else None
        )
        previous_currency = (
            previous_snapshot.currency if previous_snapshot else None
        )

        result = tracker.get_price(
            url=product.url,
            css_selector=product.css_selector,
            force_dynamic=product.force_dynamic,
        )

        if result.price is not None:
            repository.save_price_record(
                product.id, result.price, result.currency
            )
            repository.reset_failure_count(product.id)
            checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            consecutive_failures = 0
        else:
            checked_at = None
            consecutive_failures = repository.increment_failure_count(
                product.id
            )
            logger.warning(
                "Не удалось получить цену для товара %s (%s): %s "
                "(подряд неудач: %d)",
                product.name,
                product.url,
                result.error,
                consecutive_failures,
            )

        outcomes.append(
            ProductCheckOutcome(
                name=product.name,
                url=product.url,
                current_price=result.price,
                current_currency=result.currency,
                previous_price=previous_price,
                previous_currency=previous_currency,
                checked_at=checked_at,
                error=result.error,
                consecutive_failures=consecutive_failures,
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
            if (
                outcome.consecutive_failures
                >= CONSECUTIVE_FAILURES_WARNING_THRESHOLD
            ):
                lines.append(
                    f"   ⛔ Не удаётся получить цену уже "
                    f"{outcome.consecutive_failures} проверок подряд — "
                    "вероятно, сайт блокирует автоматические запросы. "
                    "Проверьте вручную: python check_price.py --dump-html"
                )
            continue

        currency_label = outcome.current_currency or DEFAULT_CURRENCY_LABEL
        line = f"• {outcome.name}: {outcome.current_price:.2f} {currency_label}"
        if outcome.previous_price is not None:
            # Сравнение корректно только если валюта не менялась между
            # проверками — для одного и того же магазина это почти
            # всегда так, смена валюты сайтом является редким случаем.
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
            currency=outcome.current_currency,
            previous_price=outcome.previous_price,
            checked_at=outcome.checked_at,
        )
        for outcome in outcomes
    ]
