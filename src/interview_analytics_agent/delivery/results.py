"""
Утилиты для работы с результатами доставки.

Назначение:
- Нормализация ошибок
- Единое представление статусов для БД/логов
"""

from __future__ import annotations

from .base import DeliveryResult


def ok_result(
    provider: str, message_id: str | None = None, meta: dict | None = None
) -> DeliveryResult:
    return DeliveryResult(ok=True, provider=provider, message_id=message_id, meta=meta)


def fail_result(provider: str, error: str, meta: dict | None = None) -> DeliveryResult:
    return DeliveryResult(ok=False, provider=provider, error=error, meta=meta)
