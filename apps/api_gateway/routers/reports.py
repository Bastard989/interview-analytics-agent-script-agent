from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
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


class ReportResponse(BaseModel):
    meeting_id: str
    report: dict[str, Any] = Field(default_factory=dict)


class ReportTextResponse(BaseModel):
    meeting_id: str
    text: str


def _report_to_text(report: dict[str, Any]) -> str:
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


def _ensure_report(meeting_id: str) -> dict[str, Any]:
    with db_session() as session:
        mrepo = MeetingRepository(session)
        srepo = TranscriptSegmentRepository(session)
        meeting = mrepo.get(meeting_id)
        if not meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

        if meeting.report:
            return dict(meeting.report)

        segs = srepo.list_by_meeting(meeting_id)
        raw = build_raw_transcript(segs)
        clean = build_enhanced_transcript(segs)
        report = build_report(enhanced_transcript=clean, meeting_context=meeting.context or {})

        meeting.raw_transcript = raw
        meeting.enhanced_transcript = clean
        meeting.report = report
        mrepo.save(meeting)

    records.write_json(meeting_id, "report.json", report)
    records.write_text(meeting_id, "report.txt", _report_to_text(report))
    return report


@router.get("/meetings/{meeting_id}/report", response_model=ReportResponse)
def get_report(meeting_id: str, _=AUTH_DEP) -> ReportResponse:
    report = _ensure_report(meeting_id)
    return ReportResponse(meeting_id=meeting_id, report=report)


@router.get("/meetings/{meeting_id}/report/text", response_model=ReportTextResponse)
def get_report_text(meeting_id: str, _=AUTH_DEP) -> ReportTextResponse:
    report = _ensure_report(meeting_id)
    text = _report_to_text(report)
    records.write_text(meeting_id, "report.txt", text)
    return ReportTextResponse(meeting_id=meeting_id, text=text)


@router.post("/meetings/{meeting_id}/report/rebuild", response_model=ReportResponse)
def rebuild_report(meeting_id: str, _=AUTH_DEP) -> ReportResponse:
    with db_session() as session:
        mrepo = MeetingRepository(session)
        meeting = mrepo.get(meeting_id)
        if not meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
        meeting.report = None
        mrepo.save(meeting)
    report = _ensure_report(meeting_id)
    return ReportResponse(meeting_id=meeting_id, report=report)
