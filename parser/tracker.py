"""
Универсальный парсер цены товара.

Логика получения HTML (откуда берём страницу):
    1. Если у товара явно указано "требует JS" (force_dynamic=True) —
       сразу используется Playwright.
    2. Иначе сначала выполняется обычный HTTP-запрос, и только если
       он не дал результата — выполняется повторная попытка через
       Playwright (для сайтов с динамической подгрузкой цены).

Логика извлечения цены из полученного HTML:
    1. Если задан CSS-селектор — сначала пробуем найти цену по нему,
       а валюту определяем по символу/сокращению рядом с числом
       (например, "$", "руб", "USD").
    2. Если селектор не задан (режим "авто") или по нему цена не
       найдена — пробуем найти цену в структурированных данных
       JSON-LD (schema.org), которые многие сайты публикуют для
       поисковых систем независимо от вёрстки страницы. Валюта в
       этом случае берётся из явного поля priceCurrency, а не
       угадывается по символу.

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
from parser.price_utils import extract_currency_symbol, parse_price
from parser.static_parser import StaticHtmlFetcher, extract_price_text

logger = logging.getLogger(__name__)


@dataclass
class PriceCheckResult:
    """Результат попытки получить цену товара."""

    price: Optional[float]
    used_dynamic: bool
    error: Optional[str] = None
    currency: Optional[str] = None


class PriceTracker:
    """Получает актуальную цену и валюту товара по URL и CSS-селектору."""

    def __init__(
        self,
        request_timeout: int = 10,
        playwright_timeout_ms: int = 15000,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._static_fetcher = StaticHtmlFetcher(
            timeout=request_timeout,
            max_retries=max_retries,
            backoff_seconds=retry_backoff_seconds,
        )
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
        Возвращает текущую цену и валюту товара на странице.

        Пустой css_selector включает режим "авто" — цена (и валюта)
        ищутся только через JSON-LD, без привязки к CSS-классу.
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

        price, currency = self._extract_price_and_currency(html, css_selector)
        if price is not None:
            return PriceCheckResult(
                price=price, used_dynamic=used_dynamic, currency=currency
            )

        return PriceCheckResult(
            price=None,
            used_dynamic=used_dynamic,
            error=self._not_found_message(css_selector),
        )

    @staticmethod
    def _extract_price_and_currency(
        html: str, css_selector: str
    ) -> Tuple[Optional[float], Optional[str]]:
        """Пробует найти цену и валюту по селектору, затем через JSON-LD."""
        if css_selector:
            price_text = extract_price_text(html, css_selector)
            price = parse_price(price_text)
            if price is not None:
                currency = extract_currency_symbol(price_text)
                return price, currency

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
