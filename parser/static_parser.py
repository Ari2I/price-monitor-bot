"""
Получение HTML обычным HTTP-запросом (для статичных сайтов, у
которых цена присутствует уже в исходном HTML-документе).

Устойчивость к временным сбоям реализована через повтор запроса с
задержкой (backoff) — но только для ошибок, которые имеет смысл
повторить (таймаут, обрыв соединения, HTTP 429/5xx). Ошибки, которые
похожи на осознанную блокировку (HTTP 403), не повторяются — это не
временный сбой, и повторные попытки только зря нагружали бы сайт.

Важно: это устойчивость к временным сбоям, а не обход защит.
Никаких механизмов обхода антибот-систем (капча, ротация IP,
подмена отпечатков браузера и т.п.) здесь нет и не будет — при
устойчивой блокировке (403) метод сразу сообщает об этом как о
вероятной блокировке, а не пытается её преодолеть.
"""

from __future__ import annotations

import logging
import time
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

# HTTP-статусы, которые считаются временными — имеет смысл повторить
# запрос после паузы. 429 (too many requests) и 5xx (ошибки на
# стороне сервера) обычно проходят сами по себе через некоторое
# время, в отличие от 403 (осознанный отказ в доступе).
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class _RetryableFetchError(HtmlFetchError):
    """
    Временная ошибка получения страницы, после которой имеет смысл
    повторить попытку (в отличие от HtmlFetchError в остальных
    случаях, который считается окончательным).
    """


class StaticHtmlFetcher(HtmlFetcher):
    """
    Загружает HTML страницы одним HTTP GET-запросом.

    При временных ошибках (таймаут, обрыв соединения, HTTP 429/5xx)
    запрос повторяется до max_retries раз с увеличивающейся паузой
    между попытками (backoff_seconds * номер попытки).
    """

    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def fetch(self, url: str) -> str:
        attempt = 0
        while True:
            try:
                return self._fetch_once(url)
            except _RetryableFetchError as exc:
                attempt += 1
                if attempt > self.max_retries:
                    # Попытки исчерпаны — превращаем во "обычную"
                    # окончательную ошибку для вызывающего кода.
                    raise HtmlFetchError(str(exc)) from exc
                wait_seconds = self.backoff_seconds * attempt
                logger.info(
                    "Временная ошибка при запросе к %s "
                    "(попытка %d из %d): %s. Повтор через %.1f с.",
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                    wait_seconds,
                )
                time.sleep(wait_seconds)

    def _fetch_once(self, url: str) -> str:
        try:
            response = requests.get(
                url, headers=DEFAULT_HEADERS, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise _RetryableFetchError(
                f"Таймаут при запросе к {url}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise _RetryableFetchError(
                f"Не удалось соединиться с {url}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            status = (
                exc.response.status_code
                if exc.response is not None
                else None
            )
            if status == 403:
                raise HtmlFetchError(
                    f"Сервер {url} вернул код 403 — вероятно, сайт "
                    "блокирует автоматические запросы (антибот-защита)"
                ) from exc
            if status in _RETRYABLE_STATUS_CODES:
                raise _RetryableFetchError(
                    f"Сервер {url} вернул временную ошибку {status}"
                ) from exc
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
