"""
Конфигурация приложения "Мониторинг цен конкурентов".

Все параметры читаются из переменных окружения (файл .env в корне
проекта). Пример заполнения — см. .env.example.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Настройки приложения."""

    bot_token: str
    database_url: str
    check_interval_minutes: int
    request_timeout: int
    attach_excel_to_scheduled_report: bool
    playwright_timeout_ms: int


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "да"}


def load_settings() -> Settings:
    """Загружает и валидирует настройки из переменных окружения."""
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Укажите токен Telegram-бота "
            "в файле .env (см. .env.example)"
        )

    return Settings(
        bot_token=bot_token,
        database_url=os.getenv("DATABASE_URL", "sqlite:///price_monitor.db"),
        check_interval_minutes=int(
            os.getenv("CHECK_INTERVAL_MINUTES", "60")
        ),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "10")),
        attach_excel_to_scheduled_report=_get_bool(
            "ATTACH_EXCEL_TO_SCHEDULED_REPORT", True
        ),
        playwright_timeout_ms=int(
            os.getenv("PLAYWRIGHT_TIMEOUT_MS", "15000")
        ),
    )
