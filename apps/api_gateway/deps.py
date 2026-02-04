"""
FastAPI Depends.

Сюда выносим:
- проверку авторизации (X-API-Key)
- (в будущем) correlation_id, request_id и т.д.
"""

from __future__ import annotations

from fastapi import Header

from interview_analytics_agent.common.security import require_api_key


def auth_dep(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """
    Проверка X-API-Key (или пропуск, если AUTH_MODE=none).
    """
    require_api_key(x_api_key)
