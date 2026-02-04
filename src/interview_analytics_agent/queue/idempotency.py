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

from interview_analytics_agent.common.config import get_settings

from .redis import redis_client

_settings = get_settings()

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
    r = redis_client()
    ok = r.set(name=key, value="1", nx=True, ex=ttl_sec)
    return bool(ok)
