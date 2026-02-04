"""
Контракты WebSocket-событий (runtime, Python-описание).

Зачем:
- удобные именованные поля/ключи
- единая точка, чтобы не разъезжались названия событий
- облегчает валидацию и поддержку версий
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .versions import WS_SCHEMA_VERSION

# =============================================================================
# ТИПЫ СОБЫТИЙ
# =============================================================================
WSEventType = Literal["audio.chunk", "transcript.update", "error"]


# =============================================================================
# ВХОД: audio.chunk (client -> server)
# =============================================================================
@dataclass
class AudioChunkEvent:
    schema_version: Literal[WS_SCHEMA_VERSION]
    event_type: Literal["audio.chunk"]

    meeting_id: str
    seq: int
    timestamp_ms: int

    codec: str
    sample_rate: int
    channels: int

    content_b64: str  # base64 аудио (MVP)
    speaker_hint: str | None = None
    idempotency_key: str | None = None


# =============================================================================
# ВЫХОД: transcript.update (server -> client)
# =============================================================================
@dataclass
class TranscriptUpdateEvent:
    schema_version: Literal[WS_SCHEMA_VERSION]
    event_type: Literal["transcript.update"]

    meeting_id: str
    seq: int
    speaker: str | None

    raw_text: str
    enhanced_text: str
    confidence: float | None = None


# =============================================================================
# ВЫХОД: error (server -> client)
# =============================================================================
@dataclass
class ErrorEvent:
    schema_version: Literal[WS_SCHEMA_VERSION]
    event_type: Literal["error"]

    code: str
    message: str
