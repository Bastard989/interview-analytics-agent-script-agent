"""
Базовые интерфейсы доставки.

Назначение:
- Единый контракт для разных каналов (email/webhook/slack и т.д.)
- Возможность переключения провайдера через ENV
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class DeliveryResult:
    """
    Результат доставки.
    """

    ok: bool
    provider: str
    message_id: str | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class DeliveryProvider(Protocol):
    """
    Контракт провайдера доставки.
    """

    def send_report(
        self,
        *,
        meeting_id: str,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,  # (filename, bytes, mime)
    ) -> DeliveryResult: ...
