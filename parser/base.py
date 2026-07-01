"""
Базовые абстракции для получения HTML-содержимого страницы.

Реализация раздельных "источников" HTML (обычный HTTP-запрос и
рендеринг через headless-браузер) позволяет боту работать как со
статичными сайтами, так и с сайтами, требующими выполнения
JavaScript — без изменения остальной логики приложения.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class HtmlFetchError(Exception):
    """Исключение при ошибке получения HTML-страницы."""


class HtmlFetcher(ABC):
    """Абстрактный источник HTML-содержимого страницы по URL."""

    @abstractmethod
    def fetch(self, url: str) -> str:
        """
        Возвращает HTML-содержимое страницы.

        Исключения:
            HtmlFetchError: при сетевой ошибке, таймауте или
            неожиданном статусе ответа.
        """
        raise NotImplementedError
