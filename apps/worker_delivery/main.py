"""
Worker Delivery.

Алгоритм (MVP):
- BLPOP из q:delivery
- читает Meeting + report
- рендерит шаблоны Jinja2
- отправляет через SMTP (если настроено)
- обновляет статус (в MVP: логируем и меняем статус встречи на done)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger, setup_logging
from interview_analytics_agent.delivery.email.sender import SMTPEmailProvider
from interview_analytics_agent.domain.enums import PipelineStatus
from interview_analytics_agent.queue.dispatcher import Q_DELIVERY, enqueue_retention
from interview_analytics_agent.queue.redis import redis_client
from interview_analytics_agent.queue.retry import requeue_with_backoff
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.repositories import MeetingRepository

log = get_project_logger()


def _jinja() -> Environment:
    tpl_dir = Path("src/interview_analytics_agent/delivery/email/templates")
    return Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def run_loop() -> None:
    settings = get_settings()
    r = redis_client()
    env = _jinja()
    smtp = SMTPEmailProvider()

    log.info("worker_delivery_started", extra={"payload": {"queue": Q_DELIVERY}})

    while True:
        item = r.brpop(Q_DELIVERY, timeout=5)
        if not item:
            continue

        _, raw = item
        try:
            task = json.loads(raw)
            meeting_id = task["meeting_id"]

            with db_session() as session:
                mrepo = MeetingRepository(session)
                m = mrepo.get(meeting_id)

                report = (m.report if m else None) or {
                    "summary": "",
                    "bullets": [],
                    "risk_flags": [],
                    "recommendation": "",
                }
                recipients = []
                if m and isinstance(m.context, dict):
                    # Если ты захочешь — потом положим recipients в context при /meetings/start
                    recipients = m.context.get("recipients", []) or []

                html = env.get_template("report.html.j2").render(
                    meeting_id=meeting_id, report=report
                )
                txt = env.get_template("report.txt.j2").render(meeting_id=meeting_id, report=report)

                if settings.delivery_provider == "email" and recipients:
                    smtp.send_report(
                        meeting_id=meeting_id,
                        recipients=recipients,
                        subject=f"Отчёт по встрече {meeting_id}",
                        html_body=html,
                        text_body=txt,
                        attachments=None,
                    )
                    log.info(
                        "delivery_done",
                        extra={"meeting_id": meeting_id, "payload": {"recipients": recipients}},
                    )
                else:
                    # В MVP, если нет получателей — считаем доставку пропущенной
                    log.warning(
                        "delivery_skipped",
                        extra={
                            "meeting_id": meeting_id,
                            "payload": {
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

        except Exception as e:
            log.error(
                "worker_delivery_error", extra={"payload": {"err": str(e)[:200], "raw": raw[:300]}}
            )
            try:
                task = task if "task" in locals() else {"raw": raw}
                requeue_with_backoff(
                    queue_name=Q_DELIVERY, task_payload=task, max_attempts=3, backoff_sec=2
                )
            except Exception:
                pass


def main() -> None:
    setup_logging()
    while True:
        try:
            run_loop()
        except Exception as e:
            log.error("worker_delivery_fatal", extra={"payload": {"err": str(e)[:200]}})
            time.sleep(2)


if __name__ == "__main__":
    main()
