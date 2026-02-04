"""
Обёртки авторизации.

Сейчас используем require_api_key из common/security.py.
Файл оставляем для будущего расширения (JWT, роли, ACL).
"""

from __future__ import annotations

from fastapi import Header

from interview_analytics_agent.common.security import require_api_key


def check_auth(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    require_api_key(x_api_key)
