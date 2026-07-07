"""
Обработчики команд Telegram-бота.

Бот получает готовые экземпляры ProductRepository и PriceTracker
через workflow_data диспетчера aiogram (см. main.py) — это позволяет
не создавать глобальные объекты внутри модуля и упрощает
тестирование.

Диалог добавления товара (/add) построен на инлайн-кнопках, а не на
свободном тексте — это исключает опечатки в духе "да"/"нет"/"авто" и
делает выбор однозначным. Перед сохранением товара бот сразу
проверяет, находится ли цена выбранным способом, и показывает
результат — это позволяет сразу увидеть, сработал ли автоматический
режим или указанный CSS-селектор, не дожидаясь /report.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.states import AddProductStates
from database.repository import ProductRepository
from export.excel_export import export_report_to_excel
from parser.tracker import PriceTracker
from reporting import (
    CONSECUTIVE_FAILURES_WARNING_THRESHOLD,
    build_report_rows,
    build_text_report,
    check_products_for_chat,
)

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = (
    "🤖 Бот мониторинга цен конкурентов\n\n"
    "Команды:\n"
    "/add — добавить товар для отслеживания (пошагово, с кнопками)\n"
    "/list — показать отслеживаемые товары\n"
    "/remove ID — удалить товар, например: /remove 3\n"
    "/report — получить отчёт по ценам прямо сейчас\n"
    "/excel — выгрузить отчёт в Excel-файл\n"
    "/history ID — история цены товара, например: /history 3\n"
    "/cancel — отменить текущий диалог\n\n"
    "Бот рассчитан на обычные интернет-магазины (на Tilda, InSales, "
    "Bitrix и похожих платформах). Крупные площадки с антибот-защитой "
    "(Wildberries, Ozon, Яндекс.Маркет, Lamoda и подобные) в рамках "
    "этого проекта не поддерживаются — на них часто не удаётся "
    "получить цену даже автоматически."
)

# Домены крупных площадок с известной антибот-защитой — бот не
# пытается их поддерживать (сознательное решение, см. README), но
# предупреждает пользователя заранее, чтобы не тратить время на
# попытки настройки того, что скорее всего не заработает.
_KNOWN_DIFFICULT_DOMAINS = (
    "wildberries.ru",
    "ozon.ru",
    "market.yandex.ru",
    "lamoda.ru",
)


def _is_known_difficult_url(url: str) -> bool:
    """Проверяет, относится ли ссылка к сайту с известной антибот-защитой."""
    domain = urlparse(url).netloc.lower()
    return any(marker in domain for marker in _KNOWN_DIFFICULT_DOMAINS)


def _mode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора способа поиска цены."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Найти цену автоматически",
                    callback_data="add_mode:auto",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Указать CSS-селектор вручную",
                    callback_data="add_mode:manual",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="add_mode:cancel"
                )
            ],
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения после успешно найденной цены."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сохранить", callback_data="add_confirm:save"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Попробовать другой способ",
                    callback_data="add_confirm:retry",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="add_confirm:cancel"
                )
            ],
        ]
    )


def _retry_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура на случай, если цену найти не удалось."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Указать CSS-селектор вручную",
                    callback_data="add_confirm:manual",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="add_confirm:cancel"
                )
            ],
        ]
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
        "Добавляем товар (шаг 1 из 3).\n\n"
        "Введите название товара — это для вашего собственного "
        "списка, в отчётах и на сайте продавца оно не отображается. "
        "Или /cancel для отмены:"
    )


@router.message(StateFilter(AddProductStates.waiting_for_name))
async def add_product_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым. Повторите:")
        return
    await state.update_data(name=name)
    await state.set_state(AddProductStates.waiting_for_url)
    await message.answer(
        "Шаг 2 из 3.\n\n"
        "Пришлите ссылку на страницу товара (полный адрес, "
        "начинающийся с http:// или https://):"
    )


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
    await state.set_state(AddProductStates.choosing_selector_mode)

    text = "Шаг 3 из 3. Как искать цену на странице?"
    if _is_known_difficult_url(url):
        text += (
            "\n\n⚠️ Это один из сайтов с известной антибот-защитой "
            "(Wildberries, Ozon, Яндекс.Маркет, Lamoda и подобные). "
            "В рамках этого бота такие сайты не поддерживаются "
            "официально — с высокой вероятностью цену найти не "
            "удастся ни автоматически, ни по CSS-селектору. Можно "
            "попробовать, но результат не гарантирован."
        )
    await message.answer(text, reply_markup=_mode_keyboard())


@router.callback_query(
    StateFilter(AddProductStates.choosing_selector_mode),
    F.data.startswith("add_mode:"),
)
async def add_product_choose_mode(
    callback: CallbackQuery,
    state: FSMContext,
    tracker: PriceTracker,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or not isinstance(
        callback.data, str
    ):
        return

    action = callback.data.split(":", maxsplit=1)[1]

    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("Добавление отменено.")
        return

    if action == "manual":
        await state.set_state(AddProductStates.waiting_for_manual_selector)
        await callback.message.edit_text(
            "Пришлите CSS-селектор цены.\n\n"
            "Как его найти: откройте страницу товара в браузере, "
            "кликните правой кнопкой мыши по цене → «Просмотреть "
            "код» (Inspect) и скопируйте класс или id элемента, "
            "например: span.price или #price-value."
        )
        return

    # action == "auto"
    await state.update_data(css_selector="")
    await _run_test_check(callback.message, state, tracker)


@router.message(StateFilter(AddProductStates.waiting_for_manual_selector))
async def add_product_manual_selector(
    message: Message,
    state: FSMContext,
    tracker: PriceTracker,
) -> None:
    selector = (message.text or "").strip()
    if not selector:
        await message.answer("Селектор не может быть пустым. Повторите:")
        return
    await state.update_data(css_selector=selector)
    await _run_test_check(message, state, tracker)


async def _run_test_check(
    message: Message, state: FSMContext, tracker: PriceTracker
) -> None:
    """Пробует найти цену прямо сейчас и показывает результат с кнопками."""
    data = await state.get_data()
    url = data["url"]
    css_selector = data["css_selector"]

    status_message = await message.answer("Проверяю цену на странице…")
    result = await asyncio.to_thread(
        tracker.get_price, url, css_selector, False
    )

    await state.set_state(AddProductStates.confirming)

    if result.price is not None:
        method = (
            "автоопределение (JSON-LD)"
            if not css_selector
            else f"селектор «{css_selector}»"
        )
        currency_label = result.currency or "₽ (не удалось определить точно)"
        await status_message.edit_text(
            f"✅ Нашёл цену: {result.price:.2f} {currency_label}\n"
            f"Способ: {method}\n\n"
            "Проверьте, что это действительно текущая цена на "
            "странице, и подтвердите сохранение:",
            reply_markup=_confirm_keyboard(),
        )
    else:
        await status_message.edit_text(
            "⚠️ Не удалось найти цену на странице.\n"
            f"Причина: {result.error}\n\n"
            "Можно указать CSS-селектор вручную или отменить "
            "добавление:",
            reply_markup=_retry_keyboard(),
        )


@router.callback_query(
    StateFilter(AddProductStates.confirming),
    F.data.startswith("add_confirm:"),
)
async def add_product_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    repository: ProductRepository,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message) or not isinstance(
        callback.data, str
    ):
        return

    action = callback.data.split(":", maxsplit=1)[1]

    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("Добавление отменено.")
        return

    if action == "manual":
        await state.set_state(AddProductStates.waiting_for_manual_selector)
        await callback.message.edit_text(
            "Пришлите CSS-селектор цены (например: span.price):"
        )
        return

    if action == "retry":
        await state.set_state(AddProductStates.choosing_selector_mode)
        await callback.message.edit_text(
            "Как искать цену на странице?", reply_markup=_mode_keyboard()
        )
        return

    # action == "save"
    data = await state.get_data()
    product = repository.add_product(
        owner_chat_id=callback.message.chat.id,
        name=data["name"],
        url=data["url"],
        css_selector=data["css_selector"],
        force_dynamic=False,
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Товар «{product.name}» добавлен (id={product.id}).\n\n"
        "Он будет проверяться автоматически по расписанию. "
        "Проверить прямо сейчас — командой /report."
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
        snapshot = repository.get_latest_price_snapshot(product.id)
        if snapshot is None:
            price_text = "нет данных"
        else:
            currency_label = snapshot.currency or "₽"
            price_text = f"{snapshot.price:.2f} {currency_label}"

        line = f"#{product.id} {product.name} — {price_text}"
        if product.consecutive_failures >= CONSECUTIVE_FAILURES_WARNING_THRESHOLD:
            line += (
                f"\n   ⛔ {product.consecutive_failures} неудачных "
                "проверок подряд — вероятна блокировка сайта"
            )
        lines.append(line)
    await message.answer("\n".join(lines))


@router.message(Command("remove"))
async def cmd_remove(message: Message, repository: ProductRepository) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "Использование: /remove ID_товара, например: /remove 3\n"
            "Посмотреть ID можно командой /list"
        )
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
        await message.answer(
            "Использование: /history ID_товара, например: /history 3\n"
            "Посмотреть ID можно командой /list"
        )
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
        currency_label = record.currency or "₽"
        lines.append(
            f"{record.checked_at:%Y-%m-%d %H:%M} — "
            f"{record.price:.2f} {currency_label}"
        )
    await message.answer("\n".join(lines))


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer(
        "Не понял команду. Список доступных команд — /help"
    )
