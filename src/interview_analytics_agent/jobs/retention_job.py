"""
Фоновая job ретеншна.

Назначение:
- периодически вычищать данные по политикам хранения
"""

from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.retention import apply_retention

log = get_project_logger()


def run() -> None:
    log.info("retention_job_started")
    with db_session() as s:
        apply_retention(s)
    log.info("retention_job_finished")
