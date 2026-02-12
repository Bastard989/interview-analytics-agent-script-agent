from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api_gateway.routers.analysis import router as analysis_router
from interview_analytics_agent.common.config import get_settings


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(analysis_router, prefix="/v1")
    return TestClient(app)


def test_scorecard_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("apps.api_gateway.routers.analysis._meeting_exists", lambda _m: True)
    monkeypatch.setattr(
        "apps.api_gateway.routers.analysis._ensure_report",
        lambda _m: {"scorecard": {"overall_score": 3.7, "competencies": []}},
    )
    monkeypatch.setattr("apps.api_gateway.routers.analysis.records.write_json", lambda *_a, **_k: None)

    settings = get_settings()
    snapshot_auth = settings.auth_mode
    snapshot_audit = settings.security_audit_db_enabled
    try:
        settings.auth_mode = "none"
        settings.security_audit_db_enabled = False
        client = _client()
        resp = client.get("/v1/meetings/m-1/scorecard")
        assert resp.status_code == 200
        assert resp.json()["scorecard"]["overall_score"] == 3.7
    finally:
        settings.auth_mode = snapshot_auth
        settings.security_audit_db_enabled = snapshot_audit


def test_comparison_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("apps.api_gateway.routers.analysis._meeting_exists", lambda _m: True)
    monkeypatch.setattr(
        "apps.api_gateway.routers.analysis._ensure_report",
        lambda meeting_id: {
            "scorecard": {"overall_score": 4.1 if meeting_id == "m-1" else 3.2, "competencies": []},
            "risk_flags": [],
        },
    )
    monkeypatch.setattr("apps.api_gateway.routers.analysis.records.write_json", lambda *_a, **_k: None)

    settings = get_settings()
    snapshot_auth = settings.auth_mode
    snapshot_audit = settings.security_audit_db_enabled
    try:
        settings.auth_mode = "none"
        settings.security_audit_db_enabled = False
        client = _client()
        resp = client.post("/v1/analysis/comparison", json={"meeting_ids": ["m-1", "m-2"]})
        assert resp.status_code == 200
        ranking = resp.json()["report"]["ranking"]
        assert ranking[0] == "m-1"
    finally:
        settings.auth_mode = snapshot_auth
        settings.security_audit_db_enabled = snapshot_audit


def test_calibration_review_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("apps.api_gateway.routers.analysis._meeting_exists", lambda _m: True)
    monkeypatch.setattr(
        "apps.api_gateway.routers.analysis._ensure_report",
        lambda _m: {
            "scorecard": {
                "overall_score": 4.0,
                "competencies": [{"competency_id": "technical_depth", "score": 4.0}],
            }
        },
    )
    monkeypatch.setattr("apps.api_gateway.routers.analysis.records.write_json", lambda *_a, **_k: None)
    monkeypatch.setattr("apps.api_gateway.routers.analysis._load_reviews", lambda _m: [])
    monkeypatch.setattr("apps.api_gateway.routers.analysis._save_reviews", lambda _m, _r: None)

    settings = get_settings()
    snapshot_auth = settings.auth_mode
    snapshot_audit = settings.security_audit_db_enabled
    try:
        settings.auth_mode = "none"
        settings.security_audit_db_enabled = False
        client = _client()
        resp = client.post(
            "/v1/meetings/m-1/calibration/review",
            json={
                "reviewer_id": "senior-1",
                "scores": {"technical_depth": 3.0},
                "decision": "hold",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["calibration"]["review_count"] == 0
    finally:
        settings.auth_mode = snapshot_auth
        settings.security_audit_db_enabled = snapshot_audit
