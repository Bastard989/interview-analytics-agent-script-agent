"""
Сидинг тестовой встречи в БД.
Используется для ручных проверок и dev-отладки.
"""

from interview_analytics_agent.common.ids import new_meeting_id
from interview_analytics_agent.domain.enums import ConsentStatus, PipelineStatus
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.models import Meeting

with db_session() as s:
    m = Meeting(
        id=new_meeting_id(),
        status=PipelineStatus.queued,
        consent=ConsentStatus.granted,
        context={"seed": True},
    )
    s.add(m)
    print("Seeded meeting:", m.id)
