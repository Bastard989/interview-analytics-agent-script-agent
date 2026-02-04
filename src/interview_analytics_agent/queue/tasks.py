"""
Контракты задач очереди.

Правила:
- payload должен быть JSON-совместимым
- поле schema_version обязательно (для эволюции контрактов)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SchemaV1 = Literal["v1"]


@dataclass
class STTTask:
    schema_version: SchemaV1
    meeting_id: str
    chunk_seq: int
    blob_key: str
    timestamp: str


@dataclass
class EnhanceTask:
    schema_version: SchemaV1
    meeting_id: str


@dataclass
class AnalyticsTask:
    schema_version: SchemaV1
    meeting_id: str


@dataclass
class DeliveryTask:
    schema_version: SchemaV1
    meeting_id: str


@dataclass
class RetentionTask:
    schema_version: SchemaV1
    entity_type: str
    entity_id: str
    reason: str
