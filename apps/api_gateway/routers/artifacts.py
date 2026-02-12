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


def _report_to_text(report: dict) -> str:
    bullets = report.get("bullets") or []
    risks = report.get("risk_flags") or []
    lines = [
        f"Summary: {report.get('summary', '')}",
        "",
        "Bullets:",
    ]
    for item in bullets:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Risk Flags:")
    for item in risks:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(f"Recommendation: {report.get('recommendation', '')}")
    return "\n".join(lines).strip() + "\n"


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
        report = build_report(enhanced_transcript=clean, meeting_context=meeting.context or {})

        meeting.raw_transcript = raw
        meeting.enhanced_transcript = clean
        meeting.report = report
        mrepo.save(meeting)

    records.write_text(meeting_id, "raw.txt", raw)
    records.write_text(meeting_id, "clean.txt", clean)
    records.write_json(meeting_id, "report.json", report)
    records.write_text(meeting_id, "report.txt", _report_to_text(report))
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
    kind: Literal["raw", "clean", "report"] = Query(default="raw"),
    fmt: Literal["txt", "json"] = Query(default="txt"),
    _=AUTH_DEP,
) -> FileResponse:
    if kind in {"raw", "clean"} and fmt != "txt":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format_required")
    if kind == "report" and fmt not in {"txt", "json"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format_required")

    if kind == "raw":
        filename = "raw.txt"
    elif kind == "clean":
        filename = "clean.txt"
    else:
        filename = "report.json" if fmt == "json" else "report.txt"

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
    return FileResponse(path, media_type=media_type, filename=path.name)
