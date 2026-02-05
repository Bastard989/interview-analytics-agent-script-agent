from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.api_gateway.tenancy import apply_tenant_to_context, enforce_meeting_access
from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.security import AuthContext


@pytest.fixture()
def tenant_settings():
    s = get_settings()
    keys = [
        "tenant_enforcement_enabled",
        "tenant_claim_key",
        "tenant_context_key",
        "jwt_service_claim_key",
        "jwt_service_claim_values",
    ]
    snapshot = {k: getattr(s, k) for k in keys}
    try:
        yield s
    finally:
        for k, v in snapshot.items():
            setattr(s, k, v)


def test_tenant_disabled_is_noop(tenant_settings) -> None:
    tenant_settings.tenant_enforcement_enabled = False
    ctx = AuthContext(subject="user-1", auth_type="api_key")
    context = apply_tenant_to_context(ctx, {"foo": "bar"})
    assert context == {"foo": "bar"}

    enforce_meeting_access(ctx, {"tenant_id": "x"})


def test_tenant_enabled_applies_claim(tenant_settings) -> None:
    tenant_settings.tenant_enforcement_enabled = True
    tenant_settings.tenant_claim_key = "tenant_id"
    tenant_settings.tenant_context_key = "tenant_id"

    ctx = AuthContext(subject="user-1", auth_type="jwt", claims={"tenant_id": "t-1"})
    context = apply_tenant_to_context(ctx, {})
    assert context["tenant_id"] == "t-1"

    meeting = SimpleNamespace(context={"tenant_id": "t-1"})
    enforce_meeting_access(ctx, meeting.context)


def test_tenant_missing_claim_denied(tenant_settings) -> None:
    tenant_settings.tenant_enforcement_enabled = True
    tenant_settings.tenant_claim_key = "tenant_id"
    tenant_settings.tenant_context_key = "tenant_id"

    ctx = AuthContext(subject="user-1", auth_type="jwt", claims={})
    with pytest.raises(HTTPException) as exc:
        apply_tenant_to_context(ctx, {})
    assert exc.value.status_code == 403


def test_tenant_mismatch_denied(tenant_settings) -> None:
    tenant_settings.tenant_enforcement_enabled = True
    tenant_settings.tenant_claim_key = "tenant_id"
    tenant_settings.tenant_context_key = "tenant_id"

    ctx = AuthContext(subject="user-1", auth_type="jwt", claims={"tenant_id": "t-1"})
    with pytest.raises(HTTPException) as exc:
        enforce_meeting_access(ctx, {"tenant_id": "t-2"})
    assert exc.value.status_code == 403
