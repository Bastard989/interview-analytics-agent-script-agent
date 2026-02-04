"""
SMTP-отправка email.

Назначение:
- Доставка отчётов по почте
- Поддержка HTML + text
- (опционально) вложения

Важно:
- Не логировать содержимое писем/транскриптов
- Логировать только метаданные (кому, статус, message-id)
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.delivery.base import DeliveryProvider, DeliveryResult
from interview_analytics_agent.delivery.results import fail_result, ok_result

log = get_project_logger()


class SMTPEmailProvider(DeliveryProvider):
    def __init__(self) -> None:
        self.s = get_settings()

    def send_report(
        self,
        *,
        meeting_id: str,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> DeliveryResult:
        if not recipients:
            return fail_result("smtp", "recipients_empty")

        if not self.s.smtp_host:
            return fail_result("smtp", "SMTP_HOST_not_set")

        msg = EmailMessage()
        msg["From"] = self.s.email_from
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        # Текстовая часть (fallback)
        msg.set_content(text_body or "Отчёт во вложении/HTML-версии.")

        # HTML часть
        msg.add_alternative(html_body, subtype="html")

        # Вложения
        if attachments:
            for filename, content, mime in attachments:
                maintype, _, subtype = mime.partition("/")
                maintype = maintype or "application"
                subtype = subtype or "octet-stream"
                msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                # STARTTLS, если порт стандартный и сервер поддерживает
                try:
                    smtp.starttls()
                    smtp.ehlo()
                except Exception:
                    # Для некоторых серверов/портов может быть без TLS в dev
                    pass

                if self.s.smtp_user and self.s.smtp_pass:
                    smtp.login(self.s.smtp_user, self.s.smtp_pass)

                smtp.send_message(msg)

            log.info(
                "email_sent",
                extra={"meeting_id": meeting_id, "payload": {"to": recipients, "provider": "smtp"}},
            )
            return ok_result("smtp", message_id=msg.get("Message-ID"))
        except Exception as e:
            log.error(
                "email_send_failed",
                extra={
                    "meeting_id": meeting_id,
                    "payload": {"to": recipients, "err": str(e)[:200]},
                },
            )
            return fail_result("smtp", str(e))
