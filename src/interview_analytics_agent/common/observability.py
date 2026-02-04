"""
Observability bootstrap.

Назначение:
- централизованно включить логирование/метрики/otel (если надо)
- не тянуть лишние зависимости внутрь apps/*
"""

from __future__ import annotations

from interview_analytics_agent.common.logging import get_project_logger, setup_logging

log = get_project_logger()


def setup_observability() -> None:
    """
    Вызывается на старте процесса (api/worker).
    Сейчас: только логирование.
    Метрики/OTEL подключаются отдельными вызовами.
    """
    setup_logging()
    log.info("observability_ready")
