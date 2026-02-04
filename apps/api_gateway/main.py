"""
API Gateway (FastAPI).

Функции:
- /health
- /metrics
- HTTP API для встреч
- WebSocket для приёма аудио чанков и отдачи transcript.update

Архитектурно:
- WS принимает audio.chunk -> сохраняет в локальное хранилище -> ставит задачу STT
- воркеры публикуют обновления в Redis pubsub channel ws:<meeting_id>
- WS подписывается на канал и пушит transcript.update клиенту
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api_gateway.routers.admin import router as admin_router
from apps.api_gateway.routers.meetings import router as meetings_router
from apps.api_gateway.routers.realtime import router as realtime_router
from apps.api_gateway.ws import ws_router
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.common.metrics import setup_metrics_endpoint
from interview_analytics_agent.common.observability import setup_observability
from interview_analytics_agent.common.otel import maybe_setup_otel

log = get_project_logger()


def _parse_origins(raw: str) -> list[str]:
    origins = [o.strip() for o in (raw or "").split(",") if o.strip()]
    return origins or ["*"]


def _is_prod_env(app_env: str | None) -> bool:
    env = (app_env or "").strip().lower()
    return env in {"prod", "production"}


def _cors_params() -> tuple[list[str], bool]:
    settings = get_settings()
    allow_origins = _parse_origins(settings.cors_allowed_origins)
    allow_credentials = bool(settings.cors_allow_credentials)

    if _is_prod_env(settings.app_env) and "*" in allow_origins:
        raise RuntimeError("CORS wildcard '*' запрещён в APP_ENV=prod")

    # '*' нельзя использовать вместе с credentials=true
    if "*" in allow_origins:
        allow_credentials = False

    return allow_origins, allow_credentials


def _create_app() -> FastAPI:
    app = FastAPI(title="Interview Analytics Agent", version="0.1.0")
    allow_origins, allow_credentials = _cors_params()

    # CORS (настраивается через ENV; в prod wildcard запрещён)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=allow_credentials,
    )

    setup_metrics_endpoint(app)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    app.include_router(meetings_router, prefix="/v1")
    app.include_router(realtime_router, prefix="/v1")
    app.include_router(admin_router, prefix="/v1")
    app.include_router(ws_router, prefix="/v1")

    return app


setup_logging()
setup_observability()
maybe_setup_otel()

# Автосоздание таблиц в dev (чтобы проект стартовал без ручных миграций)
log.info("db_ready")

app = _create_app()
