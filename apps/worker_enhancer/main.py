"""
Worker Enhancer.

Алгоритм (MVP):
- BLPOP из q:enhancer
- берём все сегменты встречи
- прогоняем enhance_text, обновляем enhanced_text
- публикуем transcript.update (по каждому сегменту)
- ставим задачу analytics
"""

from __future__ import annotations

import json
import time

from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.processing.enhancer import enhance_text
from interview_analytics_agent.processing.quality import quality_score
from interview_analytics_agent.queue.dispatcher import Q_ENHANCER, enqueue_analytics
from interview_analytics_agent.queue.redis import redis_client
from interview_analytics_agent.queue.retry import requeue_with_backoff
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import TranscriptSegmentRepository

log = get_project_logger()


def _publish_update(meeting_id: str, payload: dict) -> None:
    redis_client().publish(f"ws:{meeting_id}", json.dumps(payload, ensure_ascii=False))


def run_loop() -> None:
    r = redis_client()
    log.info("worker_enhancer_started", extra={"payload": {"queue": Q_ENHANCER}})

    while True:
        item = r.brpop(Q_ENHANCER, timeout=5)
        if not item:
            continue

        _, raw = item
        try:
            task = json.loads(raw)
            meeting_id = task["meeting_id"]

            with db_session() as session:
                srepo = TranscriptSegmentRepository(session)
                segs = srepo.list_by_meeting(meeting_id)

                for seg in segs:
                    enh, meta = enhance_text(seg.raw_text or "")
                    if enh != (seg.enhanced_text or ""):
                        seg.enhanced_text = enh
                        q = quality_score(seg.raw_text or "", enh)
                        _publish_update(
                            meeting_id,
                            {
                                "schema_version": "v1",
                                "event_type": "transcript.update",
                                "meeting_id": meeting_id,
                                "seq": seg.seq,
                                "speaker": seg.speaker,
                                "raw_text": seg.raw_text or "",
                                "enhanced_text": seg.enhanced_text or "",
                                "confidence": seg.confidence,
                                "quality": q,
                                "meta": meta,
                            },
                        )

            enqueue_analytics(meeting_id=meeting_id)

        except Exception as e:
            log.error(
                "worker_enhancer_error", extra={"payload": {"err": str(e)[:200], "raw": raw[:300]}}
            )
            try:
                task = task if "task" in locals() else {"raw": raw}
                requeue_with_backoff(
                    queue_name=Q_ENHANCER, task_payload=task, max_attempts=3, backoff_sec=1
                )
            except Exception:
                pass


def main() -> None:
    setup_logging()
    while True:
        try:
            run_loop()
        except Exception as e:
            log.error("worker_enhancer_fatal", extra={"payload": {"err": str(e)[:200]}})
            time.sleep(2)


if __name__ == "__main__":
    main()
