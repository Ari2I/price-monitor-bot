"""
Получение HTML через headless-браузер (Playwright).

Используется для сайтов, где цена появляется на странице только
после выполнения JavaScript (динамическая подгрузка данных) — в
таких случаях обычный HTTP-запрос (см. static_parser.py) не находит
нужный элемент в исходном HTML.
"""

from __future__ import annotations

import logging

from parser.base import HtmlFetcher, HtmlFetchError

logger = logging.getLogger(__name__)


class DynamicHtmlFetcher(HtmlFetcher):
    """
    Загружает HTML страницы после её полной отрисовки в браузере.

    Playwright импортируется внутри метода fetch (а не на уровне
    модуля), чтобы приложение могло запускаться и работать со
    статичными сайтами даже в окружении, где браузеры Playwright не
    установлены — динамический парсер в этом случае просто не будет
    использоваться.
    """

    def __init__(self, timeout_ms: int = 15000) -> None:
        self.timeout_ms = timeout_ms

    def fetch(self, url: str) -> str:
        try:
            from playwright.sync_api import (
                Error as PlaywrightError,
                sync_playwright,
            )
        except ImportError as exc:
            raise HtmlFetchError(
                "Playwright не установлен. Выполните: "
                "pip install playwright && playwright install chromium"
            ) from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(
                        url,
                        timeout=self.timeout_ms,
                        wait_until="networkidle",
                    )
                    html = page.content()
                finally:
                    browser.close()
            return html
        except PlaywrightError as exc:
            raise HtmlFetchError(
                f"Не удалось загрузить {url} через браузер: {exc}"
            ) from exc
