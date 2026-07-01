"""
Планировщик автоматических проверок цен и рассылки отчётов.

Использует AsyncIOScheduler, работающий в том же event loop, что и
aiogram — это позволяет напрямую вызывать асинхронные методы бота
(отправку сообщений и файлов) из запланированных задач.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.repository import ProductRepository
from export.excel_export import export_report_to_excel
from parser.tracker import PriceTracker
from reporting import build_report_rows, build_text_report, check_products_for_chat

logger = logging.getLogger(__name__)


async def _send_scheduled_report(
    bot: Bot,
    repository: ProductRepository,
    tracker: PriceTracker,
    owner_chat_id: int,
    attach_excel: bool,
) -> None:
    outcomes = await asyncio.to_thread(
        check_products_for_chat, repository, tracker, owner_chat_id
    )
    if not outcomes:
        return

    text_report = build_text_report(outcomes)
    try:
        await bot.send_message(owner_chat_id, "⏰ " + text_report)
    except Exception:  # noqa: BLE001 — сбой у одного пользователя
        logger.exception(
            "Не удалось отправить отчёт пользователю %s", owner_chat_id
        )
        return

    if not attach_excel:
        return

    rows = build_report_rows(outcomes)
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = Path(tmp_dir) / "price_report.xlsx"
        export_report_to_excel(rows, str(file_path))
        try:
            await bot.send_document(
                owner_chat_id,
                FSInputFile(file_path, filename="price_report.xlsx"),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Не удалось отправить Excel-файл пользователю %s",
                owner_chat_id,
            )


async def run_scheduled_check(
    bot: Bot,
    repository: ProductRepository,
    tracker: PriceTracker,
    attach_excel: bool,
) -> None:
    """Проверяет цены и рассылает отчёты всем пользователям бота."""
    owner_chat_ids = repository.list_all_owner_chat_ids()
    logger.info(
        "Запуск плановой проверки цен для %d пользователей",
        len(owner_chat_ids),
    )
    for owner_chat_id in owner_chat_ids:
        await _send_scheduled_report(
            bot, repository, tracker, owner_chat_id, attach_excel
        )


def create_scheduler(
    bot: Bot,
    repository: ProductRepository,
    tracker: PriceTracker,
    interval_minutes: int,
    attach_excel: bool,
) -> AsyncIOScheduler:
    """Создаёт и настраивает планировщик (не запускает его)."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scheduled_check,
        trigger="interval",
        minutes=interval_minutes,
        kwargs={
            "bot": bot,
            "repository": repository,
            "tracker": tracker,
            "attach_excel": attach_excel,
        },
        id="price_check_job",
        replace_existing=True,
    )
    return scheduler
