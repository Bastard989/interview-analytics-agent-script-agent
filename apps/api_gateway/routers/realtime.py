"""
HTTP ingestion endpoints for post-meeting uploads.

Задача:
- принимать аудио-чанки через HTTP
- сохранять в blob storage
- ставить задачу в STT очередь
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api_gateway.deps import auth_dep, service_auth_write_dep
from apps.api_gateway.tenancy import enforce_meeting_access, tenant_enforcement_enabled
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.common.security import AuthContext
from interview_analytics_agent.common.tracing import start_trace
from interview_analytics_agent.services.chunk_ingest_service import ingest_audio_chunk_b64
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import MeetingRepository

log = get_project_logger()
router = APIRouter()


class ChunkIngestRequest(BaseModel):
    seq: int = Field(ge=0)
    content_b64: str
    codec: str = "pcm"
    sample_rate: int = 16000
    channels: int = 1
    idempotency_key: str | None = None


class ChunkIngestResponse(BaseModel):
    accepted: bool
    meeting_id: str
    seq: int
    idempotency_key: str
    blob_key: str


def _ingest_chunk_impl(meeting_id: str, req: ChunkIngestRequest) -> ChunkIngestResponse:
    with start_trace(meeting_id=meeting_id, source="http.ingest"):
        try:
            result = ingest_audio_chunk_b64(
                meeting_id=meeting_id,
                seq=req.seq,
                content_b64=req.content_b64,
                idempotency_key=req.idempotency_key,
                idempotency_scope="audio_chunk_http",
                idempotency_prefix="http-chunk",
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "bad_audio", "message": "content_b64 не декодируется"},
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "ingest_error", "message": "Ошибка ingest аудио-чанка"},
            ) from e

        log.info(
            "http_chunk_ingested",
            extra={
                "payload": {"meeting_id": meeting_id, "seq": req.seq, "codec": req.codec},
            },
        )
        return ChunkIngestResponse(
            accepted=result.accepted,
            meeting_id=result.meeting_id,
            seq=result.seq,
            idempotency_key=result.idempotency_key,
            blob_key=result.blob_key,
        )


def _ensure_meeting_access(ctx: AuthContext, meeting_id: str) -> None:
    if not tenant_enforcement_enabled():
        return
    with db_session() as s:
        repo = MeetingRepository(s)
        m = repo.get(meeting_id)
        if not m:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": "Встреча не найдена"},
            )
        enforce_meeting_access(ctx, m.context)


@router.post("/meetings/{meeting_id}/chunks", response_model=ChunkIngestResponse)
def ingest_chunk(
    meeting_id: str,
    req: ChunkIngestRequest,
    ctx: AuthContext = Depends(auth_dep),
) -> ChunkIngestResponse:
    _ensure_meeting_access(ctx, meeting_id)
    return _ingest_chunk_impl(meeting_id=meeting_id, req=req)


@router.post(
    "/internal/meetings/{meeting_id}/chunks",
    response_model=ChunkIngestResponse,
    dependencies=[Depends(service_auth_write_dep)],
)
def ingest_chunk_internal(meeting_id: str, req: ChunkIngestRequest) -> ChunkIngestResponse:
    return _ingest_chunk_impl(meeting_id=meeting_id, req=req)
