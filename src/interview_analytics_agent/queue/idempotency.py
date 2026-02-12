"""
Идемпотентность (дедупликация) событий.

Зачем нужно:
- WS может прислать один и тот же чанк повторно
- воркеры могут ретраить задачу
- важно не дублировать сегменты и артефакты

Реализация:
- хранение ключей в Redis с TTL
- ключ формируется как "<scope>:<meeting_id>:<idempotency_key>"
"""

from __future__ import annotations

import time

from interview_analytics_agent.common.config import get_settings

from .redis import redis_client

_settings = get_settings()
_LOCAL_IDEM_KEYS: dict[str, float] = {}

# TTL по умолчанию (сек) для идемпотентных ключей
DEFAULT_TTL_SEC = 60 * 60 * 24  # 24 часа


def check_and_set(
    scope: str, meeting_id: str, idem_key: str, ttl_sec: int = DEFAULT_TTL_SEC
) -> bool:
    """
    Возвращает True, если ключ НОВЫЙ (т.е. можно обрабатывать),
    и False, если ключ уже был (дедуп).

    Использует SET NX.
    """
    key = f"idem:{scope}:{meeting_id}:{idem_key}"
    if (_settings.queue_mode or "").strip().lower() == "inline":
        now = time.monotonic()
        expires = _LOCAL_IDEM_KEYS.get(key, 0.0)
        if expires > now:
            return False
        _LOCAL_IDEM_KEYS[key] = now + max(1, int(ttl_sec))
        if len(_LOCAL_IDEM_KEYS) > 20_000:
            for k, exp in list(_LOCAL_IDEM_KEYS.items()):
                if exp <= now:
                    _LOCAL_IDEM_KEYS.pop(k, None)
        return True

    r = redis_client()
    ok = r.set(name=key, value="1", nx=True, ex=ttl_sec)
    return bool(ok)
