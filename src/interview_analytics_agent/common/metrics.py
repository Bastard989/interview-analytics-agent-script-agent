"""
Метрики Prometheus для сервиса.

Назначение:
- Экспорт /metrics
- Общие счётчики и гистограммы для всех стадий пайплайна
- Используется API Gateway и воркерами
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# =============================================================================
# СЧЁТЧИКИ И МЕТРИКИ
# =============================================================================

# Общее количество HTTP-запросов
REQUESTS_TOTAL = Counter(
    "agent_requests_total",
    "Общее количество HTTP запросов",
    ["service", "route", "method", "status"],
)

# Задержки по стадиям пайплайна
PIPELINE_STAGE_LATENCY_MS = Histogram(
    "agent_pipeline_stage_latency_ms",
    "Задержка выполнения стадий пайплайна (мс)",
    ["service", "stage"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)

# Обработка задач очередей
QUEUE_TASKS_TOTAL = Counter(
    "agent_queue_tasks_total",
    "Количество обработанных задач очереди",
    ["service", "queue", "result"],
)


# =============================================================================
# ENDPOINT /metrics
# =============================================================================
def setup_metrics_endpoint(app: FastAPI) -> None:
    """
    Регистрирует endpoint /metrics для Prometheus.
    """

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
