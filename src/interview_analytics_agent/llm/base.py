"""
Базовые типы для LLM.

Проблема, которую решаем:
- orchestrator импортирует LLMProvider и LLMResult, но их не было -> ImportError.

Решение:
- определяем единый контракт провайдера
- добавляем простой результат генерации
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    """
    Результат генерации LLM.
    """

    text: str
    model: str | None = None
    usage: dict[str, Any] | None = None


class LLMProvider(ABC):
    """
    Интерфейс провайдера LLM.
    """

    @abstractmethod
    def generate(self, *, prompt: str, system: str | None = None) -> LLMResult:
        """
        Сгенерировать ответ на prompt.
        """
        raise NotImplementedError
