"""
Единый ingest-сервис для аудио-чанков.

Используется в:
- HTTP ingest endpoints
- WebSocket ingest
- внутренний live-ingest коннектора
"""

from __future__ import annotations

from dataclasses import dataclass

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.ids import new_idempotency_key
from interview_analytics_agent.common.utils import b64_decode
from interview_analytics_agent.queue.dispatcher import enqueue_stt
from interview_analytics_agent.queue.idempotency import check_and_set
from interview_analytics_agent.services.local_pipeline import process_chunk_inline
from interview_analytics_agent.storage.blob import put_bytes


@dataclass
class ChunkIngestResult:
    accepted: bool
    meeting_id: str
    seq: int
    idempotency_key: str
    blob_key: str
    is_duplicate: bool
    inline_updates: list[dict] | None = None


def ingest_audio_chunk_bytes(
    *,
    meeting_id: str,
    seq: int,
    audio_bytes: bytes,
    idempotency_key: str | None = None,
    idempotency_scope: str = "audio_chunk_http",
    idempotency_prefix: str = "http-chunk",
) -> ChunkIngestResult:
    settings = get_settings()
    idem_key = idempotency_key or new_idempotency_key(idempotency_prefix)
    blob_key = f"meetings/{meeting_id}/chunks/{seq}.bin"

    if not check_and_set(idempotency_scope, meeting_id, idem_key):
        return ChunkIngestResult(
            accepted=True,
            meeting_id=meeting_id,
            seq=seq,
            idempotency_key=idem_key,
            blob_key=blob_key,
            is_duplicate=True,
            inline_updates=[],
        )

    put_bytes(blob_key, audio_bytes)
    inline_updates: list[dict] | None = None
    if (settings.queue_mode or "").strip().lower() == "inline":
        inline_updates = process_chunk_inline(
            meeting_id=meeting_id,
            chunk_seq=seq,
            audio_bytes=audio_bytes,
            blob_key=blob_key,
        )
    else:
        enqueue_stt(meeting_id=meeting_id, chunk_seq=seq, blob_key=blob_key)
    return ChunkIngestResult(
        accepted=True,
        meeting_id=meeting_id,
        seq=seq,
        idempotency_key=idem_key,
        blob_key=blob_key,
        is_duplicate=False,
        inline_updates=inline_updates or [],
    )


def ingest_audio_chunk_b64(
    *,
    meeting_id: str,
    seq: int,
    content_b64: str,
    idempotency_key: str | None = None,
    idempotency_scope: str = "audio_chunk_http",
    idempotency_prefix: str = "http-chunk",
) -> ChunkIngestResult:
    try:
        audio_bytes = b64_decode(content_b64)
    except Exception as e:
        raise ValueError("content_b64 decode failed") from e
    return ingest_audio_chunk_bytes(
        meeting_id=meeting_id,
        seq=seq,
        audio_bytes=audio_bytes,
        idempotency_key=idempotency_key,
        idempotency_scope=idempotency_scope,
        idempotency_prefix=idempotency_prefix,
    )
