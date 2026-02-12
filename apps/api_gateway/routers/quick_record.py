from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api_gateway.deps import auth_dep
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.quick_record import (
    QuickRecordConfig,
    QuickRecordJobStatus,
    get_quick_record_manager,
)

router = APIRouter()
AUTH_DEP = Depends(auth_dep)


class QuickRecordStartRequest(BaseModel):
    meeting_url: str = Field(min_length=8)
    duration_sec: int | None = Field(default=None, ge=5, le=86_400)
    transcribe: bool = False
    transcribe_language: str = Field(default="ru", min_length=2, max_length=8)
    upload_to_agent: bool = False
    build_local_report: bool | None = None
    agent_api_key: str | None = None
    auto_open_url: bool | None = None
    email_to: list[str] = Field(default_factory=list)


class QuickRecordStartResponse(BaseModel):
    ok: bool = True
    job: QuickRecordJobStatus


class QuickRecordStatusResponse(BaseModel):
    ok: bool = True
    job: QuickRecordJobStatus | None = None


class QuickRecordStopResponse(BaseModel):
    ok: bool = True
    job: QuickRecordJobStatus | None = None


@router.post("/quick-record/start", response_model=QuickRecordStartResponse)
def quick_record_start(req: QuickRecordStartRequest, _=AUTH_DEP) -> QuickRecordStartResponse:
    s = get_settings()
    if not bool(getattr(s, "quick_record_enabled", True)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="quick_record is disabled",
        )

    manager = get_quick_record_manager()
    duration = req.duration_sec or int(getattr(s, "quick_record_default_duration_sec", 1800))
    api_key = (req.agent_api_key or getattr(s, "quick_record_agent_api_key", None) or "").strip()

    cfg = QuickRecordConfig(
        meeting_url=req.meeting_url,
        output_dir=Path(getattr(s, "quick_record_output_dir", "./recordings")),
        segment_length_sec=int(getattr(s, "quick_record_segment_length_sec", 120)),
        overlap_sec=int(getattr(s, "quick_record_overlap_sec", 30)),
        sample_rate=int(getattr(s, "quick_record_sample_rate", 44100)),
        block_size=int(getattr(s, "quick_record_block_size", 1024)),
        auto_open_url=(
            bool(getattr(s, "quick_record_auto_open_url", False))
            if req.auto_open_url is None
            else bool(req.auto_open_url)
        ),
        max_duration_sec=duration,
        transcribe=bool(req.transcribe),
        transcribe_language=req.transcribe_language,
        upload_to_agent=bool(req.upload_to_agent),
        build_local_report=(
            bool(getattr(s, "quick_record_build_local_report", True))
            if req.build_local_report is None
            else bool(req.build_local_report)
        ),
        agent_base_url=str(getattr(s, "quick_record_agent_base_url", "http://127.0.0.1:8010")),
        agent_api_key=api_key or None,
        wait_report_sec=int(getattr(s, "quick_record_wait_report_sec", 180)),
        poll_interval_sec=float(getattr(s, "quick_record_poll_interval_sec", 3.0)),
        email_to=req.email_to,
    )

    if cfg.upload_to_agent and not cfg.agent_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="upload_to_agent=true requires agent_api_key",
        )

    try:
        job = manager.start(cfg)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return QuickRecordStartResponse(job=job)


@router.get("/quick-record/status", response_model=QuickRecordStatusResponse)
def quick_record_status(job_id: str | None = None, _=AUTH_DEP) -> QuickRecordStatusResponse:
    manager = get_quick_record_manager()
    return QuickRecordStatusResponse(job=manager.get_status(job_id=job_id))


@router.post("/quick-record/stop", response_model=QuickRecordStopResponse)
def quick_record_stop(_=AUTH_DEP) -> QuickRecordStopResponse:
    manager = get_quick_record_manager()
    return QuickRecordStopResponse(job=manager.stop())
