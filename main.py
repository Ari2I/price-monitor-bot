"""
Точка входа в приложение "Мониторинг цен конкурентов".

Запуск:
    python main.py
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from bot.handlers import router
from config import load_settings
from database.repository import ProductRepository
from parser.tracker import PriceTracker
from scheduler import create_scheduler


def configure_logging() -> None:
    """Настраивает базовое логирование приложения."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def main() -> None:
    configure_logging()
    settings = load_settings()

    session = (
        AiohttpSession(proxy=settings.bot_proxy_url)
        if settings.bot_proxy_url
        else None
    )
    bot = Bot(
        token=settings.bot_token,
        session=session,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    repository = ProductRepository(settings.database_url)
    tracker = PriceTracker(
        request_timeout=settings.request_timeout,
        playwright_timeout_ms=settings.playwright_timeout_ms,
        max_retries=settings.request_max_retries,
        retry_backoff_seconds=settings.request_retry_backoff_seconds,
    )

    scheduler = create_scheduler(
        bot=bot,
        repository=repository,
        tracker=tracker,
        interval_minutes=settings.check_interval_minutes,
        attach_excel=settings.attach_excel_to_scheduled_report,
    )
    scheduler.start()

    try:
        await dispatcher.start_polling(
            bot, repository=repository, tracker=tracker
        )
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
