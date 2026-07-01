"""
Обработчики команд Telegram-бота.

Бот получает готовые экземпляры ProductRepository и PriceTracker
через workflow_data диспетчера aiogram (см. main.py) — это позволяет
не создавать глобальные объекты внутри модуля и упрощает
тестирование.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from bot.states import AddProductStates
from database.repository import ProductRepository
from export.excel_export import export_report_to_excel
from parser.tracker import PriceTracker
from reporting import (
    build_report_rows,
    build_text_report,
    check_products_for_chat,
)

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = (
    "🤖 Бот мониторинга цен конкурентов\n\n"
    "Команды:\n"
    "/add — добавить товар для отслеживания\n"
    "/list — показать отслеживаемые товары\n"
    "/remove <id> — удалить товар\n"
    "/report — получить отчёт по ценам прямо сейчас\n"
    "/excel — выгрузить отчёт в Excel-файл\n"
    "/history <id> — история цены товара\n"
    "/cancel — отменить текущий диалог"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я слежу за ценами на товары и присылаю отчёты "
        "по расписанию и по запросу.\n\n" + HELP_TEXT
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Сейчас нечего отменять.")
        return
    await state.clear()
    await message.answer("Диалог отменён.")


# ---------------------------------------------------------------------
# Диалог добавления товара (FSM)
# ---------------------------------------------------------------------
@router.message(Command("add"))
async def cmd_add_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddProductStates.waiting_for_name)
    await message.answer(
        "Введите название товара (для ваших собственных списков), "
        "или /cancel для отмены:"
    )


@router.message(StateFilter(AddProductStates.waiting_for_name))
async def add_product_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым. Повторите:")
        return
    await state.update_data(name=name)
    await state.set_state(AddProductStates.waiting_for_url)
    await message.answer("Теперь пришлите ссылку на страницу товара:")


@router.message(StateFilter(AddProductStates.waiting_for_url))
async def add_product_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "Похоже, это не ссылка. Пришлите полный URL "
            "(начинается с http:// или https://):"
        )
        return
    await state.update_data(url=url)
    await state.set_state(AddProductStates.waiting_for_selector)
    await message.answer(
        "Укажите CSS-селектор элемента с ценой на странице "
        "(например: span.price или #product-price).\n\n"
        "Если не знаете, как его найти — откройте страницу товара "
        "в браузере, кликните правой кнопкой по цене → "
        "«Просмотреть код» и скопируйте класс или id элемента."
    )


@router.message(StateFilter(AddProductStates.waiting_for_selector))
async def add_product_selector(message: Message, state: FSMContext) -> None:
    selector = (message.text or "").strip()
    if not selector:
        await message.answer("Селектор не может быть пустым. Повторите:")
        return
    await state.update_data(css_selector=selector)
    await state.set_state(AddProductStates.waiting_for_dynamic_flag)
    await message.answer(
        "Сайт подгружает цену через JavaScript (динамически), "
        "и обычный запрос её не увидит?\n"
        "Ответьте «да» или «нет». Если не уверены — ответьте «нет», "
        "бот попробует определить это автоматически."
    )


@router.message(StateFilter(AddProductStates.waiting_for_dynamic_flag))
async def add_product_dynamic_flag(
    message: Message,
    state: FSMContext,
    repository: ProductRepository,
) -> None:
    answer = (message.text or "").strip().lower()
    force_dynamic = answer in {"да", "yes", "y", "д"}

    data = await state.get_data()
    product = repository.add_product(
        owner_chat_id=message.chat.id,
        name=data["name"],
        url=data["url"],
        css_selector=data["css_selector"],
        force_dynamic=force_dynamic,
    )
    await state.clear()
    await message.answer(
        f"✅ Товар «{product.name}» добавлен (id={product.id}).\n"
        "Он будет проверяться автоматически по расписанию. "
        "Отчёт прямо сейчас — командой /report"
    )


# ---------------------------------------------------------------------
# Просмотр и удаление товаров
# ---------------------------------------------------------------------
@router.message(Command("list"))
async def cmd_list(message: Message, repository: ProductRepository) -> None:
    products = repository.list_products(message.chat.id)
    if not products:
        await message.answer(
            "Список пуст. Добавьте товар командой /add"
        )
        return

    lines = ["📦 Отслеживаемые товары:\n"]
    for product in products:
        latest_price = repository.get_latest_price(product.id)
        price_text = (
            f"{latest_price:.2f} ₽" if latest_price is not None else "нет данных"
        )
        lines.append(f"#{product.id} {product.name} — {price_text}")
    await message.answer("\n".join(lines))


@router.message(Command("remove"))
async def cmd_remove(message: Message, repository: ProductRepository) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /remove <id товара>")
        return

    product_id = int(args[1].strip())
    removed = repository.remove_product(message.chat.id, product_id)
    if removed:
        await message.answer(f"Товар #{product_id} удалён.")
    else:
        await message.answer(
            f"Товар #{product_id} не найден среди ваших товаров."
        )


# ---------------------------------------------------------------------
# Отчёты по запросу
# ---------------------------------------------------------------------
@router.message(Command("report"))
async def cmd_report(
    message: Message,
    repository: ProductRepository,
    tracker: PriceTracker,
) -> None:
    await message.answer("Проверяю актуальные цены, это может занять время…")
    outcomes = await asyncio.to_thread(
        check_products_for_chat, repository, tracker, message.chat.id
    )
    await message.answer(build_text_report(outcomes))


@router.message(Command("excel"))
async def cmd_excel(
    message: Message,
    repository: ProductRepository,
    tracker: PriceTracker,
) -> None:
    outcomes = await asyncio.to_thread(
        check_products_for_chat, repository, tracker, message.chat.id
    )
    if not outcomes:
        await message.answer(
            "Список отслеживаемых товаров пуст. Добавьте товар "
            "командой /add"
        )
        return

    rows = build_report_rows(outcomes)
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = Path(tmp_dir) / "price_report.xlsx"
        export_report_to_excel(rows, str(file_path))
        await message.answer_document(
            FSInputFile(file_path, filename="price_report.xlsx")
        )


@router.message(Command("history"))
async def cmd_history(
    message: Message, repository: ProductRepository
) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /history <id товара>")
        return

    product_id = int(args[1].strip())
    product = repository.get_product(message.chat.id, product_id)
    if product is None:
        await message.answer("Товар не найден среди ваших товаров.")
        return

    history = repository.get_price_history(product_id, limit=20)
    if not history:
        await message.answer("По этому товару пока нет истории цен.")
        return

    lines = [f"📈 История цены «{product.name}»:\n"]
    for record in history:
        lines.append(
            f"{record.checked_at:%Y-%m-%d %H:%M} — {record.price:.2f} ₽"
        )
    await message.answer("\n".join(lines))


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer(
        "Не понял команду. Список доступных команд — /help"
    )
