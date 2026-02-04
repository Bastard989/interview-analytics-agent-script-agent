"""
HTTP роуты для встреч.

MVP:
- POST /v1/meetings/start
- GET  /v1/meetings/{meeting_id}

Авторизация: Depends(auth_dep)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api_gateway.deps import auth_dep
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.contracts.http_api import (
    MeetingGetResponse,
    MeetingStartRequest,
    MeetingStartResponse,
)
from interview_analytics_agent.services.meeting_service import create_meeting
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import MeetingRepository

log = get_project_logger()

router = APIRouter()


@router.post(
    "/meetings/start", response_model=MeetingStartResponse, dependencies=[Depends(auth_dep)]
)
def start_meeting(req: MeetingStartRequest) -> MeetingStartResponse:
    with db_session() as s:
        repo = MeetingRepository(s)
        m = create_meeting(meeting_id=req.meeting_id, context=req.context, consent=req.consent)
        repo.save(m)
        log.info("meeting_created", extra={"meeting_id": m.id})
        return MeetingStartResponse(meeting_id=m.id, status=str(m.status))


@router.get(
    "/meetings/{meeting_id}", response_model=MeetingGetResponse, dependencies=[Depends(auth_dep)]
)
def get_meeting(meeting_id: str) -> MeetingGetResponse:
    with db_session() as s:
        repo = MeetingRepository(s)
        m = repo.get(meeting_id)
        if not m:
            return MeetingGetResponse(meeting_id=meeting_id, status="not_found")

        return MeetingGetResponse(
            meeting_id=m.id,
            status=str(m.status),
            raw_transcript=m.raw_transcript or "",
            enhanced_transcript=m.enhanced_transcript or "",
            report=m.report,
        )
