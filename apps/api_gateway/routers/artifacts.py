from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from apps.api_gateway.deps import auth_dep
from interview_analytics_agent.processing.aggregation import (
    build_enhanced_transcript,
    build_raw_transcript,
)
from interview_analytics_agent.processing.analytics import build_report
from interview_analytics_agent.services.report_artifacts import write_report_artifacts
from interview_analytics_agent.storage import records
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import (
    MeetingRepository,
    TranscriptSegmentRepository,
)

router = APIRouter()
AUTH_DEP = Depends(auth_dep)


class MeetingListItem(BaseModel):
    meeting_id: str
    status: str
    created_at: datetime | None
    finished_at: datetime | None
    artifacts: dict[str, bool] = Field(default_factory=dict)


class MeetingListResponse(BaseModel):
    items: list[MeetingListItem]


class MeetingArtifactsResponse(BaseModel):
    meeting_id: str
    artifacts: dict[str, bool]


def _rebuild_artifacts(meeting_id: str) -> dict[str, bool]:
    try:
        records.ensure_meeting_dir(meeting_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_meeting_id",
        ) from e

    with db_session() as session:
        mrepo = MeetingRepository(session)
        srepo = TranscriptSegmentRepository(session)
        meeting = mrepo.get(meeting_id)
        if not meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

        segs = srepo.list_by_meeting(meeting_id)
        raw = build_raw_transcript(segs)
        clean = build_enhanced_transcript(segs)
        seg_payload = [
            {
                "seq": seg.seq,
                "speaker": seg.speaker,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "raw_text": seg.raw_text,
                "enhanced_text": seg.enhanced_text,
            }
            for seg in segs
        ]
        report = build_report(
            enhanced_transcript=clean,
            meeting_context=meeting.context or {},
            transcript_segments=seg_payload,
        )

        meeting.raw_transcript = raw
        meeting.enhanced_transcript = clean
        meeting.report = report
        mrepo.save(meeting)

    write_report_artifacts(
        meeting_id=meeting_id,
        raw_text=raw,
        clean_text=clean,
        report=report,
    )
    return records.list_artifacts(meeting_id)


@router.get("/meetings", response_model=MeetingListResponse)
def list_meetings(
    limit: int = Query(default=50, ge=1, le=200),
    _=AUTH_DEP,
) -> MeetingListResponse:
    with db_session() as session:
        repo = MeetingRepository(session)
        meetings = repo.list_recent(limit=limit)

    items: list[MeetingListItem] = []
    for meeting in meetings:
        items.append(
            MeetingListItem(
                meeting_id=meeting.id,
                status=str(meeting.status),
                created_at=meeting.created_at,
                finished_at=meeting.finished_at,
                artifacts=records.list_artifacts(meeting.id),
            )
        )
    return MeetingListResponse(items=items)


@router.post("/meetings/{meeting_id}/artifacts/rebuild", response_model=MeetingArtifactsResponse)
def rebuild_meeting_artifacts(meeting_id: str, _=AUTH_DEP) -> MeetingArtifactsResponse:
    artifacts = _rebuild_artifacts(meeting_id)
    return MeetingArtifactsResponse(meeting_id=meeting_id, artifacts=artifacts)


@router.get("/meetings/{meeting_id}/artifacts", response_model=MeetingArtifactsResponse)
def get_meeting_artifacts(meeting_id: str, _=AUTH_DEP) -> MeetingArtifactsResponse:
    try:
        artifacts = records.list_artifacts(meeting_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_meeting_id",
        ) from e
    return MeetingArtifactsResponse(meeting_id=meeting_id, artifacts=artifacts)


@router.get("/meetings/{meeting_id}/artifact")
def download_artifact(
    meeting_id: str,
    kind: Literal[
        "raw",
        "clean",
        "report",
        "scorecard",
        "comparison",
        "calibration",
        "decision",
        "brief",
    ] = Query(default="raw"),
    fmt: Literal["txt", "json", "md", "html", "pdf"] = Query(default="txt"),
    _=AUTH_DEP,
) -> FileResponse:
    if kind in {"raw", "clean"} and fmt != "txt":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format_required")
    if kind in {"report", "scorecard", "comparison", "calibration", "decision"} and fmt not in {
        "txt",
        "json",
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format_required")
    if kind == "brief" and fmt not in {"txt", "md", "html", "pdf"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format_required")

    if kind == "raw":
        filename = "raw.txt"
    elif kind == "clean":
        filename = "clean.txt"
    elif kind == "report":
        filename = "report.json" if fmt == "json" else "report.txt"
    elif kind == "scorecard":
        filename = "scorecard.json"
        fmt = "json"
    elif kind == "comparison":
        filename = "comparison.json"
        fmt = "json"
    elif kind == "decision":
        filename = "decision.json"
        fmt = "json"
    elif kind == "brief":
        if fmt == "md":
            filename = "senior_brief.md"
        elif fmt == "html":
            filename = "senior_brief.html"
        elif fmt == "pdf":
            filename = "senior_brief.pdf"
        else:
            filename = "senior_brief.txt"
    else:
        filename = "calibration_report.json"
        fmt = "json"

    try:
        path = records.artifact_path(meeting_id, filename)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_meeting_id",
        ) from e

    if not path.exists():
        _rebuild_artifacts(meeting_id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact_not_found")

    media_type = "text/plain"
    if path.suffix == ".json":
        media_type = "application/json"
    elif path.suffix == ".html":
        media_type = "text/html"
    elif path.suffix == ".pdf":
        media_type = "application/pdf"
    return FileResponse(path, media_type=media_type, filename=path.name)
