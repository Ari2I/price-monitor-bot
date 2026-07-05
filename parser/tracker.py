"""
Универсальный парсер цены товара.

Логика получения HTML (откуда берём страницу):
    1. Если у товара явно указано "требует JS" (force_dynamic=True) —
       сразу используется Playwright.
    2. Иначе сначала выполняется обычный HTTP-запрос, и только если
       он не дал результата — выполняется повторная попытка через
       Playwright (для сайтов с динамической подгрузкой цены).

Логика извлечения цены из полученного HTML:
    1. Если задан CSS-селектор — сначала пробуем найти цену по нему.
    2. Если селектор не задан (режим "авто") или по нему цена не
       найдена — пробуем найти цену в структурированных данных
       JSON-LD (schema.org), которые многие сайты публикуют для
       поисковых систем независимо от вёрстки страницы.

Такой подход даёт "универсальность" без лишних затрат: большинство
интернет-магазинов отдают цену в статическом HTML, и для них не
запускается тяжёлый headless-браузер, а сам селектор указывать не
обязательно — можно положиться на автоматическое определение.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from parser.base import HtmlFetchError, HtmlFetcher
from parser.dynamic_parser import DynamicHtmlFetcher
from parser.jsonld_extractor import extract_price_from_jsonld
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
    """Получает актуальную цену товара по URL и (опционально) CSS-селектору."""

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
        css_selector: str = "",
        force_dynamic: bool = False,
    ) -> PriceCheckResult:
        """
        Возвращает текущую цену товара на странице.

        Пустой css_selector включает режим "авто" — цена ищется
        только через JSON-LD, без привязки к конкретному CSS-классу.
        """
        if force_dynamic:
            html, error = self._safe_fetch(self._dynamic_fetcher, url)
            return self._extract_or_error(
                html, error, css_selector, used_dynamic=True
            )

        html, error = self._safe_fetch(self._static_fetcher, url)
        result = self._extract_or_error(
            html, error, css_selector, used_dynamic=False
        )
        if result.price is not None:
            return result

        logger.info(
            "Цена не найдена статическим методом для %s, "
            "пробуем Playwright",
            url,
        )
        html, error = self._safe_fetch(self._dynamic_fetcher, url)
        return self._extract_or_error(
            html, error, css_selector, used_dynamic=True
        )

    def _extract_or_error(
        self,
        html: Optional[str],
        fetch_error: Optional[str],
        css_selector: str,
        used_dynamic: bool,
    ) -> PriceCheckResult:
        if html is None:
            return PriceCheckResult(
                price=None, used_dynamic=used_dynamic, error=fetch_error
            )

        price = self._extract_price(html, css_selector)
        if price is not None:
            return PriceCheckResult(price=price, used_dynamic=used_dynamic)

        return PriceCheckResult(
            price=None,
            used_dynamic=used_dynamic,
            error=self._not_found_message(css_selector),
        )

    @staticmethod
    def _extract_price(html: str, css_selector: str) -> Optional[float]:
        """Пробует найти цену по селектору, затем через JSON-LD."""
        if css_selector:
            price_text = extract_price_text(html, css_selector)
            price = parse_price(price_text)
            if price is not None:
                return price

        return extract_price_from_jsonld(html)

    @staticmethod
    def _not_found_message(css_selector: str) -> str:
        if css_selector:
            return (
                f"Не удалось найти цену по селектору '{css_selector}', "
                "а также не удалось определить её автоматически"
            )
        return "Не удалось автоматически определить цену на странице"

    @staticmethod
    def _safe_fetch(
        fetcher: HtmlFetcher, url: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Возвращает (html, None) при успехе или (None, ошибка) при сбое."""
        try:
            return fetcher.fetch(url), None
        except HtmlFetchError as exc:
            return None, str(exc)
