"""
OpenTelemetry bootstrap (безопасный).

Проблема:
- код падал, если в Settings нет поля otel_enabled.

Решение:
- читаем флаг через getattr(..., False)
- если OTEL выключен или зависимости не установлены — просто no-op
"""

from __future__ import annotations

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger

log = get_project_logger()


def maybe_setup_otel() -> None:
    """
    Включает OTEL только если OTEL_ENABLED=true и зависимости доступны.
    В MVP по умолчанию выключено.
    """
    settings = get_settings()
    enabled = bool(getattr(settings, "otel_enabled", False))
    if not enabled:
        return

    # Здесь можно подключить opentelemetry-sdk / exporter.
    # Пока оставляем заглушку, чтобы проект не падал.
    log.info("otel_enabled_but_not_configured")
