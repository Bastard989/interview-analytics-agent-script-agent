"""
Worker Analytics.

Алгоритм (MVP):
- читаем из Redis Stream q:analytics (consumer group)
- читаем сегменты встречи
- собираем enhanced_transcript
- строим report через processing.analytics (LLM orchestrator)
- сохраняем в Meeting.enhanced_transcript и Meeting.report
- ставим задачу delivery
"""

from __future__ import annotations

import time
from contextlib import suppress

from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.common.metrics import QUEUE_TASKS_TOTAL, track_stage_latency
from interview_analytics_agent.common.otel import maybe_setup_otel
from interview_analytics_agent.common.tracing import start_trace_from_payload
from interview_analytics_agent.domain.enums import PipelineStatus
from interview_analytics_agent.processing.aggregation import (
    build_enhanced_transcript,
    build_raw_transcript,
)
from interview_analytics_agent.processing.analytics import build_report
from interview_analytics_agent.queue.dispatcher import Q_ANALYTICS, enqueue_delivery
from interview_analytics_agent.queue.retry import requeue_with_backoff
from interview_analytics_agent.queue.streams import ack_task, consumer_name, read_task
from interview_analytics_agent.services.readiness_service import enforce_startup_readiness
from interview_analytics_agent.storage import records
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import (
    MeetingRepository,
    TranscriptSegmentRepository,
)

log = get_project_logger()
GROUP_ANALYTICS = "g:analytics"


def run_loop() -> None:
    consumer = consumer_name("worker-analytics")
    log.info("worker_analytics_started", extra={"payload": {"queue": Q_ANALYTICS}})

    while True:
        msg = read_task(stream=Q_ANALYTICS, group=GROUP_ANALYTICS, consumer=consumer, block_ms=5000)
        if not msg:
            continue

        should_ack = False
        try:
            task = msg.payload
            meeting_id = task["meeting_id"]
            with (
                start_trace_from_payload(task, meeting_id=meeting_id, source="worker.analytics"),
                track_stage_latency("worker-analytics", "analytics"),
            ):
                with db_session() as session:
                    mrepo = MeetingRepository(session)
                    srepo = TranscriptSegmentRepository(session)

                    m = mrepo.get(meeting_id)
                    ctx = (m.context if m else {}) or {}

                    segs = srepo.list_by_meeting(meeting_id)
                    raw = build_raw_transcript(segs)
                    enhanced = build_enhanced_transcript(segs)
                    seg_payload = [
                        {
                            "seq": seg.seq,
                            "speaker": seg.speaker,
                            "start_ms": seg.start_ms,
                            "end_ms": seg.end_ms,
                            "raw_text": seg.raw_text,
                            "enhanced_text": seg.enhanced_text,
                        }
                        for seg in segs
                    ]

                    report = build_report(
                        enhanced_transcript=enhanced,
                        meeting_context=ctx,
                        transcript_segments=seg_payload,
                    )

                    if m:
                        m.raw_transcript = raw
                        m.enhanced_transcript = enhanced
                        m.report = report
                        m.status = PipelineStatus.processing
                        mrepo.save(m)

                records.write_text(meeting_id, "raw.txt", raw)
                records.write_text(meeting_id, "clean.txt", enhanced)
                records.write_json(meeting_id, "report.json", report)
                scorecard = report.get("scorecard")
                if isinstance(scorecard, dict):
                    records.write_json(meeting_id, "scorecard.json", scorecard)

                enqueue_delivery(meeting_id=meeting_id)
            should_ack = True
            QUEUE_TASKS_TOTAL.labels(
                service="worker-analytics", queue=Q_ANALYTICS, result="success"
            ).inc()

        except Exception as e:
            log.error(
                "worker_analytics_error",
                extra={
                    "payload": {"err": str(e)[:200], "task": task if "task" in locals() else None}
                },
            )
            QUEUE_TASKS_TOTAL.labels(
                service="worker-analytics", queue=Q_ANALYTICS, result="error"
            ).inc()
            try:
                task = task if "task" in locals() else {}
                requeue_with_backoff(
                    queue_name=Q_ANALYTICS, task_payload=task, max_attempts=3, backoff_sec=2
                )
                should_ack = True
                QUEUE_TASKS_TOTAL.labels(
                    service="worker-analytics", queue=Q_ANALYTICS, result="retry"
                ).inc()
            except Exception:
                pass
        finally:
            if should_ack:
                with suppress(Exception):
                    ack_task(stream=Q_ANALYTICS, group=GROUP_ANALYTICS, entry_id=msg.entry_id)


def main() -> None:
    setup_logging()
    maybe_setup_otel()
    enforce_startup_readiness(service_name="worker-analytics")
    while True:
        try:
            run_loop()
        except Exception as e:
            log.error("worker_analytics_fatal", extra={"payload": {"err": str(e)[:200]}})
            time.sleep(2)


if __name__ == "__main__":
    main()
