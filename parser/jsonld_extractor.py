"""
Извлечение цены товара из структурированных данных JSON-LD
(schema.org Product/Offer).

Многие интернет-магазины встраивают такие данные в HTML-код
страницы специально для поисковых систем (Google, Яндекс) — чтобы
показывать цену прямо в поисковой выдаче. Эти данные не зависят от
того, как цена отображается визуально на странице, и обычно
устойчивее к редизайну сайта, чем конкретный CSS-класс.

Важная оговорка: это не гарантированный способ — не каждый сайт
публикует такие данные, а сама разметка может отличаться от
ожидаемой. Поэтому функция используется как дополнительный источник
цены, а не как замена ручного CSS-селектора.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from bs4 import BeautifulSoup

from parser.price_utils import parse_price

logger = logging.getLogger(__name__)

# Ключи, в которых schema.org обычно хранит цену товара:
# Offer.price — конкретная цена, {low,high}Price — для диапазона цен
# (например, у товара с разными вариантами).
_PRICE_KEYS = ("price", "lowPrice", "highPrice")


def extract_price_from_jsonld(html: str) -> Optional[float]:
    """
    Ищет цену товара в блоках <script type="application/ld+json">.

    Возвращает None, если структурированные данные отсутствуют,
    повреждены или не содержат распознаваемой цены.
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.debug("Не удалось разобрать JSON-LD блок как JSON")
            continue

        price = _find_price(data)
        if price is not None:
            return price

    return None


def _find_price(node: Any) -> Optional[float]:
    """Рекурсивно ищет цену в произвольной JSON-структуре."""
    if isinstance(node, dict):
        for key in _PRICE_KEYS:
            if key in node:
                price = _to_float(node[key])
                if price is not None:
                    return price
        for value in node.values():
            price = _find_price(value)
            if price is not None:
                return price
    elif isinstance(node, list):
        for item in node:
            price = _find_price(item)
            if price is not None:
                return price
    return None


def _to_float(value: Any) -> Optional[float]:
    """Приводит значение цены (число или строку) к float."""
    if isinstance(value, bool):
        # bool — подкласс int в Python, явно исключаем некорректный случай
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return parse_price(value)
    return None
