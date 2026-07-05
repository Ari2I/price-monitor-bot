"""FSM-состояния диалогов бота."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddProductStates(StatesGroup):
    """
    Пошаговый диалог добавления нового товара для отслеживания.

    Шаги: название -> ссылка -> выбор способа поиска цены (кнопки)
    -> (при ручном выборе) CSS-селектор текстом -> подтверждение
    найденной на практике цены перед сохранением в базу.
    """

    waiting_for_name = State()
    waiting_for_url = State()
    choosing_selector_mode = State()
    waiting_for_manual_selector = State()
    confirming = State()
