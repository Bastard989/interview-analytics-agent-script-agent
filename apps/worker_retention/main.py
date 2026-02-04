"""
Worker Retention.

Алгоритм (MVP):
- BLPOP из q:retention
- запускает apply_retention по БД (очистка текстов по cutoff)
- (позже) удаление объектов из локальное хранилище
"""

from __future__ import annotations

import json
import time

from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.queue.dispatcher import Q_RETENTION
from interview_analytics_agent.queue.redis import redis_client
from interview_analytics_agent.queue.retry import requeue_with_backoff
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.retention import apply_retention

log = get_project_logger()


def run_loop() -> None:
    r = redis_client()
    log.info("worker_retention_started", extra={"payload": {"queue": Q_RETENTION}})

    while True:
        item = r.brpop(Q_RETENTION, timeout=10)
        if not item:
            continue

        _, raw = item
        try:
            task = json.loads(raw)

            with db_session() as session:
                apply_retention(session)

            log.info(
                "retention_applied",
                extra={
                    "payload": {
                        "task": {
                            "entity_type": task.get("entity_type"),
                            "entity_id": task.get("entity_id"),
                        }
                    }
                },
            )

        except Exception as e:
            log.error(
                "worker_retention_error", extra={"payload": {"err": str(e)[:200], "raw": raw[:300]}}
            )
            try:
                task = task if "task" in locals() else {"raw": raw}
                requeue_with_backoff(
                    queue_name=Q_RETENTION, task_payload=task, max_attempts=3, backoff_sec=3
                )
            except Exception:
                pass


def main() -> None:
    setup_logging()
    while True:
        try:
            run_loop()
        except Exception as e:
            log.error("worker_retention_fatal", extra={"payload": {"err": str(e)[:200]}})
            time.sleep(2)


if __name__ == "__main__":
    main()
