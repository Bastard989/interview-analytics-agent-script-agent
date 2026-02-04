"""
Утилиты безопасности и авторизации.

Поддерживаемые режимы (AUTH_MODE):
- api_key — проверка X-API-Key
- jwt     — будет реализован позже
- none    — без авторизации (ТОЛЬКО dev)
"""

from __future__ import annotations

from .config import get_settings
from .errors import UnauthorizedError


def _parse_api_keys(raw: str) -> set[str]:
    """
    Разбор строки API_KEYS из ENV в множество.
    """
    return {k.strip() for k in (raw or "").split(",") if k.strip()}


def require_api_key(x_api_key: str | None) -> None:
    """
    Проверка API-ключа.

    Вызывается на уровне API Gateway.
    """
    settings = get_settings()

    if settings.auth_mode == "none":
        return

    if settings.auth_mode != "api_key":
        raise UnauthorizedError("Режим авторизации не реализован")

    allowed_keys = _parse_api_keys(settings.api_keys)

    if not x_api_key or x_api_key not in allowed_keys:
        raise UnauthorizedError("Неверный API ключ")
