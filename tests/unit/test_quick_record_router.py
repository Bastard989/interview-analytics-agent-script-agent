from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api_gateway.routers.quick_record import router as quick_record_router
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.quick_record import QuickRecordJobStatus


class _FakeManager:
    def __init__(self):
        self._status = QuickRecordJobStatus(
            job_id="qr-1",
            status="running",
            created_at="2026-02-12T12:00:00Z",
            started_at="2026-02-12T12:00:01Z",
        )
        self.started_with = None

    def start(self, cfg):
        self.started_with = cfg
        return self._status

    def get_status(self, job_id=None):
        return self._status if (job_id in {None, "qr-1"}) else None

    def stop(self):
        self._status.status = "stopping"
        return self._status


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(quick_record_router, prefix="/v1")
    return TestClient(app)


def test_quick_record_start_and_status(monkeypatch) -> None:
    fake = _FakeManager()
    monkeypatch.setattr(
        "apps.api_gateway.routers.quick_record.get_quick_record_manager",
        lambda: fake,
    )

    s = get_settings()
    snapshot_auth = s.auth_mode
    snapshot_quick = s.quick_record_enabled
    try:
        s.auth_mode = "none"
        s.quick_record_enabled = True
        client = _client()

        start = client.post(
            "/v1/quick-record/start",
            json={
                "meeting_url": "https://meet.example/123",
                "duration_sec": 15,
                "transcribe": True,
                "upload_to_agent": False,
            },
        )
        assert start.status_code == 200
        assert start.json()["job"]["job_id"] == "qr-1"
        assert fake.started_with is not None
        assert fake.started_with.max_duration_sec == 15

        status = client.get("/v1/quick-record/status")
        assert status.status_code == 200
        assert status.json()["job"]["status"] == "running"

        stop = client.post("/v1/quick-record/stop")
        assert stop.status_code == 200
        assert stop.json()["job"]["status"] == "stopping"
    finally:
        s.auth_mode = snapshot_auth
        s.quick_record_enabled = snapshot_quick


def test_quick_record_start_rejects_missing_agent_key_when_upload(monkeypatch) -> None:
    fake = _FakeManager()
    monkeypatch.setattr(
        "apps.api_gateway.routers.quick_record.get_quick_record_manager",
        lambda: fake,
    )

    s = get_settings()
    snapshot_auth = s.auth_mode
    snapshot_quick = s.quick_record_enabled
    snapshot_key = s.quick_record_agent_api_key
    try:
        s.auth_mode = "none"
        s.quick_record_enabled = True
        s.quick_record_agent_api_key = None
        client = _client()

        resp = client.post(
            "/v1/quick-record/start",
            json={
                "meeting_url": "https://meet.example/456",
                "duration_sec": 30,
                "upload_to_agent": True,
            },
        )
        assert resp.status_code == 400
    finally:
        s.auth_mode = snapshot_auth
        s.quick_record_enabled = snapshot_quick
        s.quick_record_agent_api_key = snapshot_key
