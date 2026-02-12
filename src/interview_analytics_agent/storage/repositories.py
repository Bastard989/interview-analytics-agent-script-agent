"""
Репозитории (DAO слой).

Правила:
- Никакой бизнес-логики
- Только CRUD и запросы
"""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy.orm import Session

from .models import Meeting, SecurityAuditEvent, TranscriptSegment


# =============================================================================
# MEETING REPOSITORY
# =============================================================================
class MeetingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, meeting_id: str) -> Meeting | None:
        return self.session.get(Meeting, meeting_id)

    def _default_status(self) -> str:
        # Стараемся взять значения из enum'ов, но не ломаемся если их нет/переименованы
        try:
            from interview_analytics_agent.domain.enums import PipelineStatus  # type: ignore

            # предпочитаем наиболее "ранний" статус
            for name in ("created", "new", "received", "ingest", "stt", "pending"):
                if hasattr(PipelineStatus, name):
                    v = getattr(PipelineStatus, name)
                    return v.value if hasattr(v, "value") else str(v)
            v = list(PipelineStatus)[0]
            return v.value if hasattr(v, "value") else str(v)
        except Exception:
            return "created"

    def _default_consent(self) -> str:
        try:
            from interview_analytics_agent.domain.enums import ConsentStatus  # type: ignore

            for name in ("unknown", "unset", "pending", "not_provided", "none"):
                if hasattr(ConsentStatus, name):
                    v = getattr(ConsentStatus, name)
                    return v.value if hasattr(v, "value") else str(v)
            v = list(ConsentStatus)[0]
            return v.value if hasattr(v, "value") else str(v)
        except Exception:
            return "unknown"

    def ensure(self, *, meeting_id: str, meeting_context: dict | None = None) -> Meeting:
        """Гарантирует, что Meeting существует.
        Идемпотентно: если уже есть — вернёт существующий.
        """
        m = self.get(meeting_id)
        if m:
            return m

        m = Meeting(
            id=meeting_id,
            status=self._default_status(),
            consent=self._default_consent(),
            context=meeting_context or {},
        )
        self.save(m)
        return m

    def save(self, meeting: Meeting) -> None:
        self.session.add(meeting)

    def list_active(self) -> list[Meeting]:
        return self.session.query(Meeting).filter(Meeting.finished_at.is_(None)).all()

    def list_recent(self, *, limit: int = 50) -> list[Meeting]:
        return (
            self.session.query(Meeting)
            .order_by(desc(Meeting.created_at))
            .limit(max(1, min(limit, 500)))
            .all()
        )


# =============================================================================
# TRANSCRIPT SEGMENT REPOSITORY
# =============================================================================
class TranscriptSegmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, segment: TranscriptSegment) -> None:
        self.session.add(segment)

    def upsert_by_meeting_seq(self, segment: TranscriptSegment) -> TranscriptSegment:
        """
        Идемпотентная запись сегмента по (meeting_id, seq).
        """
        existing = (
            self.session.query(TranscriptSegment)
            .filter(
                TranscriptSegment.meeting_id == segment.meeting_id,
                TranscriptSegment.seq == segment.seq,
            )
            .one_or_none()
        )
        if existing is None:
            self.session.add(segment)
            return segment

        existing.speaker = segment.speaker
        existing.start_ms = segment.start_ms
        existing.end_ms = segment.end_ms
        existing.raw_text = segment.raw_text
        existing.enhanced_text = segment.enhanced_text
        existing.confidence = segment.confidence
        return existing

    def list_by_meeting(self, meeting_id: str) -> list[TranscriptSegment]:
        return (
            self.session.query(TranscriptSegment)
            .filter(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.seq)
            .all()
        )


class SecurityAuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_event(
        self,
        *,
        outcome: str,
        endpoint: str,
        method: str,
        subject: str,
        auth_type: str,
        reason: str,
        status_code: int,
        error_code: str | None = None,
        client_ip: str | None = None,
    ) -> SecurityAuditEvent:
        event = SecurityAuditEvent(
            outcome=outcome,
            endpoint=endpoint,
            method=method,
            subject=subject,
            auth_type=auth_type,
            reason=reason,
            status_code=status_code,
            error_code=error_code,
            client_ip=client_ip,
        )
        self.session.add(event)
        return event

    def list_recent(
        self,
        *,
        limit: int = 100,
        outcome: str | None = None,
        subject: str | None = None,
    ) -> list[SecurityAuditEvent]:
        query = self.session.query(SecurityAuditEvent)
        if outcome:
            query = query.filter(SecurityAuditEvent.outcome == outcome)
        if subject:
            query = query.filter(SecurityAuditEvent.subject == subject)
        return (
            query.order_by(
                desc(SecurityAuditEvent.created_at),
                desc(SecurityAuditEvent.id),
            )
            .limit(max(1, min(limit, 500)))
            .all()
        )
