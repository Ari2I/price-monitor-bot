"""
Утилиты для извлечения числового значения цены из произвольного
текста, найденного на странице (например, "1 299,90 руб." или
"$49.99").
"""

from __future__ import annotations

import re
from typing import Optional

# Разрешённые "мусорные" символы вокруг числа: валютные значки,
# неразрывные пробелы, буквы и т.д. Само число может содержать
# пробелы/точки как разделители тысяч и запятую или точку как
# десятичный разделитель.
_PRICE_PATTERN = re.compile(
    r"(\d[\d\s\u00A0.,]*\d|\d)"
)


def parse_price(raw_text: Optional[str]) -> Optional[float]:
    """
    Извлекает цену из строки и возвращает её в виде float.

    Поддерживает распространённые форматы:
        "1 299,90 руб." -> 1299.90
        "1.299,90 ₽"    -> 1299.90
        "$49.99"        -> 49.99
        "49999"         -> 49999.0

    Если число извлечь не удалось, возвращает None.
    """
    if not raw_text:
        return None

    match = _PRICE_PATTERN.search(raw_text)
    if not match:
        return None

    number_str = match.group(1)
    # Убираем пробелы (обычные и неразрывные) — это разделители тысяч.
    number_str = number_str.replace(" ", "").replace("\u00A0", "")

    if "," in number_str and "." in number_str:
        # Оба разделителя присутствуют: последний по позиции —
        # десятичный, остальные — разделители тысяч.
        last_comma = number_str.rfind(",")
        last_dot = number_str.rfind(".")
        if last_comma > last_dot:
            number_str = number_str.replace(".", "").replace(",", ".")
        else:
            number_str = number_str.replace(",", "")
    elif "," in number_str:
        # Одна запятая — считаем её десятичным разделителем, если
        # после неё 1-2 цифры (типично для рублей и копеек),
        # иначе — разделитель тысяч.
        head, _, tail = number_str.rpartition(",")
        if len(tail) in (1, 2):
            number_str = f"{head}.{tail}"
        else:
            number_str = number_str.replace(",", "")

    try:
        return float(number_str)
    except ValueError:
        return None
