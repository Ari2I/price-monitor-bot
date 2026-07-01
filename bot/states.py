"""FSM-состояния диалогов бота."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddProductStates(StatesGroup):
    """Пошаговый диалог добавления нового товара для отслеживания."""

    waiting_for_name = State()
    waiting_for_url = State()
    waiting_for_selector = State()
    waiting_for_dynamic_flag = State()
