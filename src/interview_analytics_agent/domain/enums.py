"""
Доменные перечисления (enum).

Используются во всей системе:
- состояние пайплайна
- режимы обработки
- согласие на обработку данных
"""

from __future__ import annotations

import enum


class MeetingMode(str, enum.Enum):
    """
    Режим обработки встречи.
    """

    realtime = "realtime"
    postmeeting = "postmeeting"


class PipelineStage(str, enum.Enum):
    """
    Стадии обработки интервью.
    """

    stt = "stt"
    enhancer = "enhancer"
    analytics = "analytics"
    delivery = "delivery"
    retention = "retention"


class PipelineStatus(str, enum.Enum):
    """
    Статус стадии пайплайна.
    """

    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class ConsentStatus(str, enum.Enum):
    """
    Статус согласия на обработку данных.
    """

    unknown = "unknown"
    granted = "granted"
    denied = "denied"
