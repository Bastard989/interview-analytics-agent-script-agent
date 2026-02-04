"""
Репозитории (DAO слой).

Правила:
- Никакой бизнес-логики
- Только CRUD и запросы
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Meeting, TranscriptSegment


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


# =============================================================================
# TRANSCRIPT SEGMENT REPOSITORY
# =============================================================================
class TranscriptSegmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, segment: TranscriptSegment) -> None:
        self.session.add(segment)

    def list_by_meeting(self, meeting_id: str) -> list[TranscriptSegment]:
        return (
            self.session.query(TranscriptSegment)
            .filter(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.seq)
            .all()
        )
