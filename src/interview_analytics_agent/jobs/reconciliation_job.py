"""
Reconciliation job.

Назначение:
- догон обработки после падений
- поиск встреч со сломанным состоянием пайплайна
"""

from interview_analytics_agent.common.logging import get_project_logger

log = get_project_logger()


def run() -> None:
    log.info("reconciliation_job_started")
    # TODO: поиск зависших встреч и повторная постановка в очередь
    log.info("reconciliation_job_finished")
