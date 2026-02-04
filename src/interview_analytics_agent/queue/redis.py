"""
Redis-клиент для очередей и pub/sub.

Назначение:
- Единая точка подключения к Redis
- Используется диспетчером задач и воркерами
"""

from __future__ import annotations

import redis

from interview_analytics_agent.common.config import get_settings

_settings = get_settings()
_client: redis.Redis | None = None


def redis_client() -> redis.Redis:
    """
    Singleton Redis client.
    """
    global _client
    if _client is None:
        _client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
    return _client
