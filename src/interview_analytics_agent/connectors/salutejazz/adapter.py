"""
Адаптер SaluteJazz (заглушка).

Назначение:
- пример структуры интеграции с внешней платформой встреч
- реальная реализация будет добавлена позже (API/SDK/авторизация)
"""

from __future__ import annotations

from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.connectors.base import MeetingConnector, MeetingContext

log = get_project_logger()


class SaluteJazzConnector(MeetingConnector):
    def join(self, meeting_id: str) -> MeetingContext:
        log.info("salutejazz_join_placeholder", extra={"meeting_id": meeting_id})
        return MeetingContext(meeting_id=meeting_id)

    def leave(self, meeting_id: str) -> None:
        log.info("salutejazz_leave_placeholder", extra={"meeting_id": meeting_id})

    def fetch_recording(self, meeting_id: str):
        log.info("salutejazz_fetch_recording_placeholder", extra={"meeting_id": meeting_id})
        return None
