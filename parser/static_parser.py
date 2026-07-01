"""
Получение HTML обычным HTTP-запросом (для статичных сайтов, у
которых цена присутствует уже в исходном HTML-документе).
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from parser.base import HtmlFetcher, HtmlFetchError

logger = logging.getLogger(__name__)

# Обычный заголовок браузера — нужен только для того, чтобы сайт не
# отклонял запрос как заведомо не браузерный. Никаких механизмов
# обхода защит (ротация IP, подмена cookie и т.п.) не используется.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


class StaticHtmlFetcher(HtmlFetcher):
    """Загружает HTML страницы одним HTTP GET-запросом."""

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        try:
            response = requests.get(
                url, headers=DEFAULT_HEADERS, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise HtmlFetchError(
                f"Таймаут при запросе к {url}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise HtmlFetchError(
                f"Не удалось соединиться с {url}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise HtmlFetchError(
                f"Сервер {url} вернул ошибку: {exc}"
            ) from exc
        return response.text


def extract_price_text(html: str, css_selector: str) -> Optional[str]:
    """
    Извлекает текст элемента, найденного по CSS-селектору.

    Возвращает None, если элемент не найден на странице.
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one(css_selector)
    if element is None:
        logger.warning(
            "Селектор %r не найден на странице", css_selector
        )
        return None
    return element.get_text(strip=True)
