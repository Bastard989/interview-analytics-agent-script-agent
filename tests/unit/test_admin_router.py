from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api_gateway.main import app
from interview_analytics_agent.common.config import get_settings

jwt = pytest.importorskip("jwt")


class _FakeRedis:
    def xlen(self, stream: str) -> int:
        return 0 if stream.endswith(":dlq") else 3

    def xpending(self, stream: str, group: str) -> dict[str, int]:
        _ = stream, group
        return {"pending": 1}


@pytest.fixture()
def auth_settings():
    s = get_settings()
    keys = [
        "auth_mode",
        "api_keys",
        "service_api_keys",
        "allow_service_api_key_in_jwt_mode",
        "oidc_issuer_url",
        "oidc_jwks_url",
        "oidc_audience",
        "oidc_algorithms",
        "jwt_shared_secret",
        "jwt_clock_skew_sec",
        "jwt_service_claim_key",
        "jwt_service_claim_values",
        "jwt_service_role_claim",
        "jwt_service_allowed_roles",
    ]
    snapshot = {k: getattr(s, k) for k in keys}
    try:
        yield s
    finally:
        for k, v in snapshot.items():
            setattr(s, k, v)


def _build_hs256_token(*, secret: str, sub: str, extra_claims: dict | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "iss": "https://issuer.local",
        "aud": "interview-agent",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return str(jwt.encode(payload, secret, algorithm="HS256"))


def test_admin_queue_health_requires_service_key(monkeypatch, auth_settings) -> None:
    auth_settings.auth_mode = "api_key"
    auth_settings.api_keys = "user-1"
    auth_settings.service_api_keys = "svc-1"

    monkeypatch.setattr("apps.api_gateway.routers.admin.redis_client", lambda: _FakeRedis())

    client = TestClient(app)

    denied = client.get("/v1/admin/queues/health", headers={"X-API-Key": "user-1"})
    assert denied.status_code == 403

    ok = client.get("/v1/admin/queues/health", headers={"X-API-Key": "svc-1"})
    assert ok.status_code == 200
    data = ok.json()
    assert len(data["queues"]) == 5


def test_admin_queue_health_allows_service_jwt(monkeypatch, auth_settings) -> None:
    auth_settings.auth_mode = "jwt"
    auth_settings.jwt_shared_secret = "test-secret"
    auth_settings.oidc_algorithms = "HS256"
    auth_settings.oidc_issuer_url = "https://issuer.local"
    auth_settings.oidc_audience = "interview-agent"
    auth_settings.jwt_service_claim_key = "token_type"
    auth_settings.jwt_service_claim_values = "service,m2m"

    monkeypatch.setattr("apps.api_gateway.routers.admin.redis_client", lambda: _FakeRedis())
    client = TestClient(app)
    token = _build_hs256_token(
        secret="test-secret",
        sub="svc-account-1",
        extra_claims={"token_type": "service"},
    )

    ok = client.get("/v1/admin/queues/health", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200


def test_admin_sberjazz_endpoints_require_service_identity(monkeypatch, auth_settings) -> None:
    auth_settings.auth_mode = "api_key"
    auth_settings.api_keys = "user-1"
    auth_settings.service_api_keys = "svc-1"

    monkeypatch.setattr(
        "apps.api_gateway.routers.admin.join_sberjazz_meeting",
        lambda meeting_id: SimpleNamespace(
            meeting_id=meeting_id,
            provider="sberjazz_mock",
            connected=True,
            attempts=1,
            last_error=None,
            updated_at="2026-02-04T00:00:00+00:00",
        ),
    )
    client = TestClient(app)

    denied = client.post("/v1/admin/connectors/sberjazz/m-1/join", headers={"X-API-Key": "user-1"})
    assert denied.status_code == 403

    ok = client.post("/v1/admin/connectors/sberjazz/m-1/join", headers={"X-API-Key": "svc-1"})
    assert ok.status_code == 200


def test_admin_sberjazz_join_status_leave(monkeypatch, auth_settings) -> None:
    auth_settings.auth_mode = "api_key"
    auth_settings.service_api_keys = "svc-1"

    monkeypatch.setattr(
        "apps.api_gateway.routers.admin.join_sberjazz_meeting",
        lambda meeting_id: SimpleNamespace(
            meeting_id=meeting_id,
            provider="sberjazz_mock",
            connected=True,
            attempts=1,
            last_error=None,
            updated_at="2026-02-04T00:00:00+00:00",
        ),
    )
    monkeypatch.setattr(
        "apps.api_gateway.routers.admin.get_sberjazz_meeting_state",
        lambda meeting_id: SimpleNamespace(
            meeting_id=meeting_id,
            provider="sberjazz_mock",
            connected=True,
            attempts=1,
            last_error=None,
            updated_at="2026-02-04T00:00:01+00:00",
        ),
    )
    monkeypatch.setattr(
        "apps.api_gateway.routers.admin.leave_sberjazz_meeting",
        lambda meeting_id: SimpleNamespace(
            meeting_id=meeting_id,
            provider="sberjazz_mock",
            connected=False,
            attempts=1,
            last_error=None,
            updated_at="2026-02-04T00:00:02+00:00",
        ),
    )

    client = TestClient(app)
    headers = {"X-API-Key": "svc-1"}

    joined = client.post("/v1/admin/connectors/sberjazz/m-2/join", headers=headers)
    assert joined.status_code == 200
    assert joined.json()["connected"] is True

    status_resp = client.get("/v1/admin/connectors/sberjazz/m-2/status", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["meeting_id"] == "m-2"

    left = client.post("/v1/admin/connectors/sberjazz/m-2/leave", headers=headers)
    assert left.status_code == 200
    assert left.json()["connected"] is False
