"""
Логирование проекта.

Фиксы:
- добавлен get_llm_logger(), потому что его импортирует llm/orchestrator.py
- логирование в stdout (Docker-friendly)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any

from interview_analytics_agent.common.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_payload = getattr(record, "payload", None)
        if isinstance(extra_payload, dict):
            payload["payload"] = extra_payload
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _build_formatter() -> logging.Formatter:
    s = get_settings()
    if (s.log_format or "").lower() == "text":
        return logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    return JsonFormatter()


def setup_logging() -> None:
    s = get_settings()
    root = logging.getLogger()
    level = getattr(logging, (s.log_level or "INFO").upper(), logging.INFO)
    root.setLevel(level)

    # Не плодим хэндлеры при повторном вызове
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(_build_formatter())
    root.addHandler(handler)

    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)


def get_project_logger(name: str = "interview-analytics-agent") -> logging.Logger:
    return logging.getLogger(name)


def get_llm_logger() -> logging.Logger:
    """
    Отдельный логгер для LLM-части (удобно фильтровать/маршрутизировать).
    """
    return logging.getLogger("interview-analytics-agent.llm")
