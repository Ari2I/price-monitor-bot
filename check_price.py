"""
Диагностическая утилита: проверяет цену на одной странице напрямую,
в обход Telegram-бота.

Полезна в нескольких случаях:
1. Проверить, сработает ли автоопределение или CSS-селектор для
   конкретного сайта, прежде чем добавлять товар в бота через /add.
2. Диагностировать сетевые проблемы (например, блокировку сайта на
   VPN-адресах) — результат выводится сразу в терминал, без
   необходимости получать ответ через Telegram.
3. Сохранить реальный HTML страницы в файл (--dump-html) для ручного
   анализа — например, чтобы проверить, публикует ли сайт вообще
   структурированные данные JSON-LD, или найти актуальный CSS-класс
   цены вручную через поиск по файлу.

Примеры запуска:
    python check_price.py https://example.com/product
    python check_price.py https://example.com/product --selector "span.price"
    python check_price.py https://example.com/product --dynamic
    python check_price.py https://example.com/product --dump-html page.html
"""

from __future__ import annotations

import argparse
import logging
import sys

from parser.base import HtmlFetchError
from parser.dynamic_parser import DynamicHtmlFetcher
from parser.static_parser import StaticHtmlFetcher
from parser.tracker import PriceTracker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Проверяет цену на странице товара напрямую, без запуска "
            "Telegram-бота — удобно для отладки селектора или сетевых "
            "проблем (например, блокировки сайта на VPN-адресах)."
        )
    )
    parser.add_argument("url", help="Ссылка на страницу товара")
    parser.add_argument(
        "--selector",
        default="",
        help=(
            "CSS-селектор цены. Если не указан — используется режим "
            "\"авто\" (поиск через JSON-LD)."
        ),
    )
    parser.add_argument(
        "--dynamic",
        action="store_true",
        help="Сразу использовать headless-браузер (Playwright), "
        "без попытки обычного HTTP-запроса",
    )
    parser.add_argument(
        "--dump-html",
        metavar="PATH",
        default=None,
        help=(
            "Дополнительно сохранить полученный HTML страницы в "
            "указанный файл — для ручного анализа (поиск JSON-LD, "
            "подбор CSS-селектора). На поиск цены не влияет."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Показывать подробные логи (уровень DEBUG)",
    )
    return parser


def _dump_html(url: str, path: str, force_dynamic: bool) -> None:
    """Сохраняет сырой HTML страницы в файл для ручного анализа."""
    fetcher = DynamicHtmlFetcher() if force_dynamic else StaticHtmlFetcher()
    try:
        html = fetcher.fetch(url)
    except HtmlFetchError as exc:
        print(f"⚠️ Не удалось получить HTML для сохранения: {exc}")
        return

    with open(path, "w", encoding="utf-8") as html_file:
        html_file.write(html)
    print(f"HTML сохранён в файл: {path} ({len(html)} символов)")


def main() -> int:
    args = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.dump_html:
        _dump_html(args.url, args.dump_html, args.dynamic)

    tracker = PriceTracker()
    result = tracker.get_price(
        url=args.url,
        css_selector=args.selector,
        force_dynamic=args.dynamic,
    )

    print("-" * 60)
    print(f"URL:      {args.url}")
    print(f"Селектор: {args.selector or '(авто, через JSON-LD)'}")
    print("-" * 60)

    method_label = (
        "Playwright (браузер)" if result.used_dynamic else "обычный HTTP-запрос"
    )

    if result.price is not None:
        currency_label = result.currency or "не определена"
        print(f"✅ Цена найдена: {result.price} (валюта: {currency_label})")
        print(f"Способ получения HTML: {method_label}")
        return 0

    print(f"⚠️ Цена не найдена. Причина: {result.error}")
    print(f"Способ получения HTML: {method_label}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
