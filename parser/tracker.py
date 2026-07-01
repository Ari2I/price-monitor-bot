"""
Универсальный парсер цены товара.

Логика работы:
    1. Если у товара явно указано "требует JS" (force_dynamic=True) —
       сразу используется Playwright.
    2. Иначе сначала выполняется обычный HTTP-запрос. Если по
       заданному CSS-селектору цена не найдена (сайт подгружает её
       через JavaScript) — автоматически выполняется повторная
       попытка через Playwright.

Такой подход даёт "универсальность" без лишних затрат: большинство
интернет-магазинов отдают цену в статическом HTML, и для них не
запускается тяжёлый headless-браузер.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from parser.base import HtmlFetchError
from parser.dynamic_parser import DynamicHtmlFetcher
from parser.price_utils import parse_price
from parser.static_parser import StaticHtmlFetcher, extract_price_text

logger = logging.getLogger(__name__)


@dataclass
class PriceCheckResult:
    """Результат попытки получить цену товара."""

    price: Optional[float]
    used_dynamic: bool
    error: Optional[str] = None


class PriceTracker:
    """Получает актуальную цену товара по URL и CSS-селектору."""

    def __init__(
        self,
        request_timeout: int = 10,
        playwright_timeout_ms: int = 15000,
    ) -> None:
        self._static_fetcher = StaticHtmlFetcher(timeout=request_timeout)
        self._dynamic_fetcher = DynamicHtmlFetcher(
            timeout_ms=playwright_timeout_ms
        )

    def get_price(
        self,
        url: str,
        css_selector: str,
        force_dynamic: bool = False,
    ) -> PriceCheckResult:
        """Возвращает текущую цену товара на странице."""
        if force_dynamic:
            return self._fetch_with(
                self._dynamic_fetcher, url, css_selector, used_dynamic=True
            )

        static_result = self._fetch_with(
            self._static_fetcher, url, css_selector, used_dynamic=False
        )
        if static_result.price is not None:
            return static_result

        logger.info(
            "Цена не найдена статическим методом для %s, "
            "пробуем Playwright",
            url,
        )
        return self._fetch_with(
            self._dynamic_fetcher, url, css_selector, used_dynamic=True
        )

    @staticmethod
    def _fetch_with(
        fetcher,
        url: str,
        css_selector: str,
        used_dynamic: bool,
    ) -> PriceCheckResult:
        try:
            html = fetcher.fetch(url)
        except HtmlFetchError as exc:
            return PriceCheckResult(
                price=None, used_dynamic=used_dynamic, error=str(exc)
            )

        price_text = extract_price_text(html, css_selector)
        price = parse_price(price_text)
        if price is None:
            return PriceCheckResult(
                price=None,
                used_dynamic=used_dynamic,
                error=(
                    f"Не удалось найти цену по селектору "
                    f"'{css_selector}'"
                ),
            )
        return PriceCheckResult(price=price, used_dynamic=used_dynamic)
