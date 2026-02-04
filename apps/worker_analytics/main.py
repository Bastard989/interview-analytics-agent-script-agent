"""
Worker Analytics.

Алгоритм (MVP):
- BLPOP из q:analytics
- читаем сегменты встречи
- собираем enhanced_transcript
- строим report через processing.analytics (LLM orchestrator)
- сохраняем в Meeting.enhanced_transcript и Meeting.report
- ставим задачу delivery
"""

from __future__ import annotations

import json
import time

from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.domain.enums import PipelineStatus
from interview_analytics_agent.processing.aggregation import build_enhanced_transcript
from interview_analytics_agent.processing.analytics import build_report
from interview_analytics_agent.queue.dispatcher import Q_ANALYTICS, enqueue_delivery
from interview_analytics_agent.queue.redis import redis_client
from interview_analytics_agent.queue.retry import requeue_with_backoff
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import (
    MeetingRepository,
    TranscriptSegmentRepository,
)

log = get_project_logger()


def run_loop() -> None:
    r = redis_client()
    log.info("worker_analytics_started", extra={"payload": {"queue": Q_ANALYTICS}})

    while True:
        item = r.brpop(Q_ANALYTICS, timeout=5)
        if not item:
            continue

        _, raw = item
        try:
            task = json.loads(raw)
            meeting_id = task["meeting_id"]

            with db_session() as session:
                mrepo = MeetingRepository(session)
                srepo = TranscriptSegmentRepository(session)

                m = mrepo.get(meeting_id)
                ctx = (m.context if m else {}) or {}

                segs = srepo.list_by_meeting(meeting_id)
                enhanced = build_enhanced_transcript(segs)

                report = build_report(enhanced_transcript=enhanced, meeting_context=ctx)

                if m:
                    m.enhanced_transcript = enhanced
                    m.report = report
                    m.status = PipelineStatus.processing
                    mrepo.save(m)

            enqueue_delivery(meeting_id=meeting_id)

        except Exception as e:
            log.error(
                "worker_analytics_error", extra={"payload": {"err": str(e)[:200], "raw": raw[:300]}}
            )
            try:
                task = task if "task" in locals() else {"raw": raw}
                requeue_with_backoff(
                    queue_name=Q_ANALYTICS, task_payload=task, max_attempts=3, backoff_sec=2
                )
            except Exception:
                pass


def main() -> None:
    setup_logging()
    while True:
        try:
            run_loop()
        except Exception as e:
            log.error("worker_analytics_fatal", extra={"payload": {"err": str(e)[:200]}})
            time.sleep(2)


if __name__ == "__main__":
    main()
