"""
Диспетчер очередей.

Назначение:
- Единые имена очередей
- Унифицированная упаковка задач в JSON
- Удобные функции enqueue_* для всех стадий пайплайна
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from interview_analytics_agent.common.ids import new_event_id
from interview_analytics_agent.common.logging import get_project_logger

from .redis import redis_client

log = get_project_logger()

# =============================================================================
# ИМЕНА ОЧЕРЕДЕЙ (Redis lists)
# =============================================================================
Q_STT = "q:stt"
Q_ENHANCER = "q:enhancer"
Q_ANALYTICS = "q:analytics"
Q_DELIVERY = "q:delivery"
Q_RETENTION = "q:retention"

# DLQ
Q_DLQ = "q:dlq"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def enqueue_stt(*, meeting_id: str, chunk_seq: int, blob_key: str) -> str:
    """
    Поставить задачу STT на обработку аудио-чанка.
    """
    event_id = new_event_id("stt")
    payload = {
        "schema_version": "v1",
        "event_id": event_id,
        "meeting_id": meeting_id,
        "chunk_seq": chunk_seq,
        "blob_key": blob_key,
        "timestamp": _now_iso(),
    }
    redis_client().lpush(Q_STT, json.dumps(payload, ensure_ascii=False))
    log.info("enqueue_stt", extra={"meeting_id": meeting_id, "payload": {"chunk_seq": chunk_seq}})
    return event_id


def enqueue_enhancer(*, meeting_id: str) -> str:
    """
    Поставить задачу улучшения текста.
    """
    event_id = new_event_id("enh")
    payload = {"schema_version": "v1", "event_id": event_id, "meeting_id": meeting_id}
    redis_client().lpush(Q_ENHANCER, json.dumps(payload, ensure_ascii=False))
    log.info("enqueue_enhancer", extra={"meeting_id": meeting_id})
    return event_id


def enqueue_analytics(*, meeting_id: str) -> str:
    """
    Поставить задачу аналитики/отчёта.
    """
    event_id = new_event_id("anl")
    payload = {"schema_version": "v1", "event_id": event_id, "meeting_id": meeting_id}
    redis_client().lpush(Q_ANALYTICS, json.dumps(payload, ensure_ascii=False))
    log.info("enqueue_analytics", extra={"meeting_id": meeting_id})
    return event_id


def enqueue_delivery(*, meeting_id: str) -> str:
    """
    Поставить задачу доставки результатов.
    """
    event_id = new_event_id("dlv")
    payload = {"schema_version": "v1", "event_id": event_id, "meeting_id": meeting_id}
    redis_client().lpush(Q_DELIVERY, json.dumps(payload, ensure_ascii=False))
    log.info("enqueue_delivery", extra={"meeting_id": meeting_id})
    return event_id


def enqueue_retention(*, entity_type: str, entity_id: str, reason: str) -> str:
    """
    Поставить задачу ретеншна (очистки).
    """
    event_id = new_event_id("ret")
    payload = {
        "schema_version": "v1",
        "event_id": event_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "reason": reason,
    }
    redis_client().lpush(Q_RETENTION, json.dumps(payload, ensure_ascii=False))
    log.info("enqueue_retention", extra={"payload": payload})
    return event_id
