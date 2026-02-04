"""
Сервисный слой: управление встречами.

Назначение:
- создание/получение встреч
- обновление статусов
- единая точка бизнес-логики вокруг Meeting
"""

from __future__ import annotations

from interview_analytics_agent.common.ids import new_meeting_id
from interview_analytics_agent.domain.enums import ConsentStatus, PipelineStatus
from interview_analytics_agent.storage.models import Meeting


def create_meeting(*, meeting_id: str | None, context: dict, consent: ConsentStatus) -> Meeting:
    """
    Создаёт ORM объект Meeting (без сохранения в БД).
    """
    mid = meeting_id or new_meeting_id()
    return Meeting(
        id=mid,
        status=PipelineStatus.queued,
        consent=consent,
        context=context or {},
        raw_transcript="",
        enhanced_transcript="",
        report=None,
    )
