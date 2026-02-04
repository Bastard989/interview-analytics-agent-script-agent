"""
Reconciliation job.

Назначение:
- поддержание коннектора в устойчивом состоянии
- поиск stale-сессий и авто-reconnect
"""

from __future__ import annotations

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.services.sberjazz_service import (
    SberJazzReconcileResult,
    reconcile_sberjazz_sessions,
)

log = get_project_logger()


def run(*, limit: int | None = None) -> SberJazzReconcileResult | None:
    settings = get_settings()
    if not settings.reconciliation_enabled:
        log.info("reconciliation_job_skipped", extra={"payload": {"reason": "disabled"}})
        return None

    reconcile_limit = int(limit if limit is not None else settings.reconciliation_limit)
    log.info("reconciliation_job_started", extra={"payload": {"limit": reconcile_limit}})

    result = reconcile_sberjazz_sessions(limit=max(1, reconcile_limit))
    log.info(
        "reconciliation_job_finished",
        extra={
            "payload": {
                "scanned": result.scanned,
                "stale": result.stale,
                "reconnected": result.reconnected,
                "failed": result.failed,
            }
        },
    )
    return result
