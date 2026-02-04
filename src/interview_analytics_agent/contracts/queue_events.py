"""
Контракты событий очередей (runtime, Python-описание).

Важно:
- payload всегда JSON
- schema_version обязателен
- event_id полезен для трассировки и дебага
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .versions import QUEUE_SCHEMA_VERSION

SchemaV1 = Literal[QUEUE_SCHEMA_VERSION]


@dataclass
class BaseQueueEvent:
    schema_version: SchemaV1
    event_id: str
    meeting_id: str
    attempts: int = 0


@dataclass
class STTQueueEvent(BaseQueueEvent):
    queue: Literal["stt"] = "stt"
    chunk_seq: int = 0
    blob_key: str = ""
    timestamp: str = ""


@dataclass
class EnhancerQueueEvent(BaseQueueEvent):
    queue: Literal["enhancer"] = "enhancer"


@dataclass
class AnalyticsQueueEvent(BaseQueueEvent):
    queue: Literal["analytics"] = "analytics"


@dataclass
class DeliveryQueueEvent(BaseQueueEvent):
    queue: Literal["delivery"] = "delivery"


@dataclass
class RetentionQueueEvent:
    schema_version: SchemaV1
    event_id: str
    entity_type: str
    entity_id: str
    reason: str
    attempts: int = 0
