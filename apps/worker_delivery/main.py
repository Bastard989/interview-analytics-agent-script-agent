"""
Worker Delivery.

Алгоритм (MVP):
- читаем из Redis Stream q:delivery (consumer group)
- читает Meeting + report
- рендерит шаблоны Jinja2
- отправляет через SMTP (если настроено)
- обновляет статус (в MVP: логируем и меняем статус встречи на done)
"""

from __future__ import annotations

import time
from contextlib import suppress
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.common.metrics import QUEUE_TASKS_TOTAL, track_stage_latency
from interview_analytics_agent.common.otel import maybe_setup_otel
from interview_analytics_agent.common.tracing import start_trace_from_payload
from interview_analytics_agent.delivery.email.sender import SMTPEmailProvider
from interview_analytics_agent.domain.enums import PipelineStatus
from interview_analytics_agent.queue.dispatcher import Q_DELIVERY, enqueue_retention
from interview_analytics_agent.queue.retry import requeue_with_backoff
from interview_analytics_agent.queue.streams import ack_task, consumer_name, read_task
from interview_analytics_agent.services.readiness_service import enforce_startup_readiness
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import MeetingRepository

log = get_project_logger()
GROUP_DELIVERY = "g:delivery"
_TRANSCRIPT_ATTACHMENT_MIME = "text/plain"


def _build_transcript_attachments(
    *, raw_text: str, enhanced_text: str
) -> list[tuple[str, bytes, str]]:
    attachments: list[tuple[str, bytes, str]] = []
    if raw_text.strip():
        attachments.append(
            ("raw_transcript.txt", raw_text.encode("utf-8"), _TRANSCRIPT_ATTACHMENT_MIME)
        )
    if enhanced_text.strip():
        attachments.append(
            ("enhanced_transcript.txt", enhanced_text.encode("utf-8"), _TRANSCRIPT_ATTACHMENT_MIME)
        )
    return attachments


def _jinja() -> Environment:
    tpl_dir = Path("src/interview_analytics_agent/delivery/email/templates")
    return Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def run_loop() -> None:
    settings = get_settings()
    consumer = consumer_name("worker-delivery")
    env = _jinja()
    smtp = SMTPEmailProvider()

    log.info("worker_delivery_started", extra={"payload": {"queue": Q_DELIVERY}})

    while True:
        msg = read_task(stream=Q_DELIVERY, group=GROUP_DELIVERY, consumer=consumer, block_ms=5000)
        if not msg:
            continue

        should_ack = False
        try:
            task = msg.payload
            meeting_id = task["meeting_id"]
            with (
                start_trace_from_payload(task, meeting_id=meeting_id, source="worker.delivery"),
                track_stage_latency("worker-delivery", "delivery"),
            ):
                with db_session() as session:
                    mrepo = MeetingRepository(session)
                    m = mrepo.get(meeting_id)

                    report = (m.report if m else None) or {
                        "summary": "",
                        "bullets": [],
                        "risk_flags": [],
                        "recommendation": "",
                    }
                    raw_transcript = (m.raw_transcript if m else None) or ""
                    enhanced_transcript = (m.enhanced_transcript if m else None) or ""
                    recipients = []
                    if m and isinstance(m.context, dict):
                        # Если ты захочешь — потом положим recipients в context при /meetings/start
                        recipients = m.context.get("recipients", []) or []

                    html = env.get_template("report.html.j2").render(
                        meeting_id=meeting_id,
                        report=report,
                        has_raw=bool(raw_transcript.strip()),
                        has_enhanced=bool(enhanced_transcript.strip()),
                    )
                    txt = env.get_template("report.txt.j2").render(
                        meeting_id=meeting_id,
                        report=report,
                        has_raw=bool(raw_transcript.strip()),
                        has_enhanced=bool(enhanced_transcript.strip()),
                    )
                    attachments = _build_transcript_attachments(
                        raw_text=raw_transcript, enhanced_text=enhanced_transcript
                    )

                    if settings.delivery_provider == "email" and recipients:
                        smtp.send_report(
                            meeting_id=meeting_id,
                            recipients=recipients,
                            subject=f"Отчёт по встрече {meeting_id}",
                            html_body=html,
                            text_body=txt,
                            attachments=attachments,
                        )
                        log.info(
                            "delivery_done",
                            extra={"payload": {"meeting_id": meeting_id, "recipients": recipients}},
                        )
                    else:
                        # В MVP, если нет получателей — считаем доставку пропущенной
                        log.warning(
                            "delivery_skipped",
                            extra={
                                "payload": {
                                    "meeting_id": meeting_id,
                                    "provider": settings.delivery_provider,
                                    "recipients": recipients,
                                },
                            },
                        )

                    if m:
                        m.status = PipelineStatus.done
                        mrepo.save(m)

                enqueue_retention(
                    entity_type="meeting", entity_id=meeting_id, reason="delivered_or_skipped"
                )
            should_ack = True
            QUEUE_TASKS_TOTAL.labels(
                service="worker-delivery", queue=Q_DELIVERY, result="success"
            ).inc()

        except Exception as e:
            log.error(
                "worker_delivery_error",
                extra={
                    "payload": {"err": str(e)[:200], "task": task if "task" in locals() else None}
                },
            )
            QUEUE_TASKS_TOTAL.labels(
                service="worker-delivery", queue=Q_DELIVERY, result="error"
            ).inc()
            try:
                task = task if "task" in locals() else {}
                requeue_with_backoff(
                    queue_name=Q_DELIVERY, task_payload=task, max_attempts=3, backoff_sec=2
                )
                should_ack = True
                QUEUE_TASKS_TOTAL.labels(
                    service="worker-delivery", queue=Q_DELIVERY, result="retry"
                ).inc()
            except Exception:
                pass
        finally:
            if should_ack:
                with suppress(Exception):
                    ack_task(stream=Q_DELIVERY, group=GROUP_DELIVERY, entry_id=msg.entry_id)


def main() -> None:
    setup_logging()
    maybe_setup_otel()
    enforce_startup_readiness(service_name="worker-delivery")
    while True:
        try:
            run_loop()
        except Exception as e:
            log.error("worker_delivery_fatal", extra={"payload": {"err": str(e)[:200]}})
            time.sleep(2)


if __name__ == "__main__":
    main()
