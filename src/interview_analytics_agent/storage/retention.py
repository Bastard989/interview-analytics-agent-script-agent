"""
Логика ретеншна данных.

Назначение:
- Очистка устаревших аудио
- Очистка сырых транскриптов
- Соблюдение политик хранения
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from interview_analytics_agent.common.config import get_settings

from .models import Meeting


def apply_retention(session: Session) -> None:
    """
    Применение политик ретеншна к данным.
    """
    settings = get_settings()
    cutoff_text = datetime.utcnow() - timedelta(days=settings.retention_days_text)

    meetings = session.query(Meeting).all()

    for meeting in meetings:
        if meeting.created_at < cutoff_text:
            meeting.raw_transcript = ""
