from interview_analytics_agent.domain.enums import ConsentStatus, PipelineStatus
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.models import Meeting


def test_db_session_context_manager_smoke():
    with db_session() as s:
        # просто проверяем, что session создаётся
        assert s is not None

        # НЕ вставляем запись (в CI можно подключить test контейнер позже)
        m = Meeting(
            id="test_meeting",
            status=PipelineStatus.queued,
            consent=ConsentStatus.unknown,
            context={},
            raw_transcript="",
            enhanced_transcript="",
            report=None,
        )
        assert m.id == "test_meeting"
