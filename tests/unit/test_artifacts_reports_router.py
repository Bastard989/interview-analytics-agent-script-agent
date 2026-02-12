from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api_gateway.routers.artifacts import router as artifacts_router
from apps.api_gateway.routers.reports import router as reports_router
from interview_analytics_agent.common.config import get_settings


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(artifacts_router, prefix="/v1")
    app.include_router(reports_router, prefix="/v1")
    return TestClient(app)


def test_list_meetings(monkeypatch) -> None:
    @contextmanager
    def _fake_db_session():
        yield object()

    class _FakeMeetingRepo:
        def __init__(self, _session):
            pass

        def list_recent(self, *, limit: int = 50):
            _ = limit
            return [
                SimpleNamespace(
                    id="m-1",
                    status="done",
                    created_at=None,
                    finished_at=None,
                )
            ]

    monkeypatch.setattr("apps.api_gateway.routers.artifacts.db_session", _fake_db_session)
    monkeypatch.setattr("apps.api_gateway.routers.artifacts.MeetingRepository", _FakeMeetingRepo)
    monkeypatch.setattr(
        "apps.api_gateway.routers.artifacts.records.list_artifacts",
        lambda meeting_id: {"raw": meeting_id == "m-1"},
    )

    s = get_settings()
    snapshot_auth = s.auth_mode
    snapshot_audit = s.security_audit_db_enabled
    try:
        s.auth_mode = "none"
        s.security_audit_db_enabled = False
        client = _client()
        resp = client.get("/v1/meetings")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["meeting_id"] == "m-1"
        assert body["items"][0]["artifacts"]["raw"] is True
    finally:
        s.auth_mode = snapshot_auth
        s.security_audit_db_enabled = snapshot_audit


def test_get_report_and_report_text(monkeypatch) -> None:
    report = {
        "summary": "ok",
        "bullets": ["b1"],
        "risk_flags": [],
        "recommendation": "none",
    }
    monkeypatch.setattr("apps.api_gateway.routers.reports._ensure_report", lambda _m: report)
    monkeypatch.setattr("apps.api_gateway.routers.reports.records.write_text", lambda *_a, **_k: None)

    s = get_settings()
    snapshot_auth = s.auth_mode
    snapshot_audit = s.security_audit_db_enabled
    try:
        s.auth_mode = "none"
        s.security_audit_db_enabled = False
        client = _client()
        json_resp = client.get("/v1/meetings/m-1/report")
        assert json_resp.status_code == 200
        assert json_resp.json()["report"]["summary"] == "ok"

        txt_resp = client.get("/v1/meetings/m-1/report/text")
        assert txt_resp.status_code == 200
        assert "Summary: ok" in txt_resp.json()["text"]
    finally:
        s.auth_mode = snapshot_auth
        s.security_audit_db_enabled = snapshot_audit
