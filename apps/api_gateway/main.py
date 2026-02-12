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

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.api_gateway.routers.admin import router as admin_router
from apps.api_gateway.routers.analysis import router as analysis_router
from apps.api_gateway.routers.artifacts import router as artifacts_router
from apps.api_gateway.routers.manual_delivery import router as manual_delivery_router
from apps.api_gateway.routers.meetings import router as meetings_router
from apps.api_gateway.routers.quick_record import router as quick_record_router
from apps.api_gateway.routers.realtime import router as realtime_router
from apps.api_gateway.routers.reports import router as reports_router
from apps.api_gateway.ws import ws_router
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.common.metrics import setup_metrics_endpoint
from interview_analytics_agent.common.observability import setup_observability
from interview_analytics_agent.common.otel import maybe_setup_otel
from interview_analytics_agent.common.tracing import current_trace_id, start_trace
from interview_analytics_agent.services.local_pipeline import warmup_stt_provider_async
from interview_analytics_agent.services.readiness_service import enforce_startup_readiness

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
    settings = get_settings()

    # CORS (настраивается через ENV; в prod wildcard запрещён)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=allow_credentials,
    )

    setup_metrics_endpoint(app)

    @app.middleware("http")
    async def tracing_middleware(request: Request, call_next):
        inbound_trace_id = request.headers.get("x-trace-id")
        with start_trace(trace_id=inbound_trace_id, source="http"):
            response = await call_next(request)
            trace_id = current_trace_id()
            if trace_id:
                response.headers["X-Trace-Id"] = trace_id
            return response

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.on_event("startup")
    async def startup_warmup() -> None:
        queue_mode = (settings.queue_mode or "").strip().lower()
        if queue_mode != "inline":
            return
        if (settings.stt_provider or "").strip().lower() != "whisper_local":
            return
        warmup_stt_provider_async()

    ui_dir = Path(__file__).parent / "ui"
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")

        @app.get("/")
        def ui_index() -> FileResponse:
            return FileResponse(ui_dir / "index.html")

    app.include_router(meetings_router, prefix="/v1")
    app.include_router(artifacts_router, prefix="/v1")
    app.include_router(reports_router, prefix="/v1")
    app.include_router(analysis_router, prefix="/v1")
    app.include_router(manual_delivery_router, prefix="/v1")
    app.include_router(quick_record_router, prefix="/v1")
    app.include_router(realtime_router, prefix="/v1")
    app.include_router(admin_router, prefix="/v1")
    app.include_router(ws_router, prefix="/v1")

    return app


setup_logging()
setup_observability()
maybe_setup_otel()
enforce_startup_readiness(service_name="api-gateway")

# Автосоздание таблиц в dev (чтобы проект стартовал без ручных миграций)
log.info("db_ready")

app = _create_app()
