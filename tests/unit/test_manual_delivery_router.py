from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api_gateway.routers.manual_delivery import router as manual_delivery_router
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.delivery.base import DeliveryResult


class _FakeSMTP:
    def send_report(
        self,
        *,
        meeting_id: str,
        recipients: list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
        from_email: str | None = None,
    ) -> DeliveryResult:
        _ = (meeting_id, recipients, subject, html_body, text_body, attachments, from_email)
        return DeliveryResult(ok=True, provider="smtp", message_id="msg-1")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(manual_delivery_router, prefix="/v1")
    return TestClient(app)


def test_list_accounts_and_manual_send(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.api_gateway.routers.manual_delivery._ensure_report",
        lambda _m: {"summary": "ok", "recommendation": "ship", "scorecard": {"overall_score": 4.1}},
    )
    monkeypatch.setattr("apps.api_gateway.routers.manual_delivery.SMTPEmailProvider", _FakeSMTP)
    monkeypatch.setattr(
        "apps.api_gateway.routers.manual_delivery.build_attachments",
        lambda **_k: [("report.json", b"{}", "application/json")],
    )
    monkeypatch.setattr("apps.api_gateway.routers.manual_delivery.append_delivery_log", lambda **_k: None)
    monkeypatch.setattr("apps.api_gateway.routers.manual_delivery.records.write_json", lambda *_a, **_k: None)

    s = get_settings()
    snapshot = {
        "auth_mode": s.auth_mode,
        "security_audit_db_enabled": s.security_audit_db_enabled,
        "delivery_sender_accounts": s.delivery_sender_accounts,
    }
    try:
        s.auth_mode = "none"
        s.security_audit_db_enabled = False
        s.delivery_sender_accounts = "default:hr@example.com,team:team@example.com"

        client = _client()
        accounts_resp = client.get("/v1/delivery/accounts")
        assert accounts_resp.status_code == 200
        assert len(accounts_resp.json()["accounts"]) == 2

        send_resp = client.post(
            "/v1/meetings/m-1/delivery/manual",
            json={
                "channel": "email",
                "sender_account": "team",
                "recipients": ["a@example.com", "b@example.com"],
                "include_artifacts": ["report_json"],
            },
        )
        assert send_resp.status_code == 200
        payload = send_resp.json()
        assert payload["ok"] is True
        assert payload["sender_account"] == "team"
        assert payload["provider_result"]["ok"] is True
    finally:
        s.auth_mode = snapshot["auth_mode"]
        s.security_audit_db_enabled = snapshot["security_audit_db_enabled"]
        s.delivery_sender_accounts = snapshot["delivery_sender_accounts"]
