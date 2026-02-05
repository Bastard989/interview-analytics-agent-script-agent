from __future__ import annotations

import pytest

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.services.readiness_service import (
    enforce_startup_readiness,
    evaluate_readiness,
)


def test_readiness_prod_fails_on_none_auth_and_local_storage() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.auth_require_jwt_in_prod,
        s.storage_mode,
        s.storage_require_shared_in_prod,
        s.cors_allowed_origins,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "none"
        s.auth_require_jwt_in_prod = True
        s.storage_mode = "local_fs"
        s.storage_require_shared_in_prod = True
        s.cors_allowed_origins = "*"
        state = evaluate_readiness()
        codes = {i.code for i in state.issues}
        assert state.ready is False
        assert "auth_none_in_prod" in codes
        assert "auth_mode_must_be_jwt_in_prod" in codes
        assert "storage_not_shared_fs" in codes
        assert "cors_wildcard_in_prod" in codes
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.auth_require_jwt_in_prod,
            s.storage_mode,
            s.storage_require_shared_in_prod,
            s.cors_allowed_origins,
        ) = snapshot


def test_readiness_dev_allows_defaults() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.storage_mode,
        s.api_keys,
    )
    try:
        s.app_env = "dev"
        s.auth_mode = "api_key"
        s.storage_mode = "local_fs"
        s.api_keys = "dev-key"
        state = evaluate_readiness()
        # warning'и допустимы, важно что нет ошибок.
        assert state.ready is True
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.storage_mode,
            s.api_keys,
        ) = snapshot


def test_startup_readiness_fail_fast_in_prod() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.readiness_fail_fast_in_prod,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "none"
        s.readiness_fail_fast_in_prod = True
        with pytest.raises(RuntimeError, match="auth_none_in_prod"):
            enforce_startup_readiness(service_name="api-gateway")
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.readiness_fail_fast_in_prod,
        ) = snapshot


def test_startup_readiness_no_fail_fast_in_prod() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.readiness_fail_fast_in_prod,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "none"
        s.readiness_fail_fast_in_prod = False
        state = enforce_startup_readiness(service_name="worker-stt")
        assert state.ready is False
        assert any(i.code == "auth_none_in_prod" for i in state.issues)
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.readiness_fail_fast_in_prod,
        ) = snapshot


def test_readiness_prod_jwt_fallback_enabled_is_warning() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.allow_service_api_key_in_jwt_mode,
        s.oidc_issuer_url,
        s.oidc_jwks_url,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "jwt"
        s.allow_service_api_key_in_jwt_mode = True
        s.oidc_issuer_url = "https://issuer.local"
        s.oidc_jwks_url = None
        state = evaluate_readiness()
        issue = next(
            (i for i in state.issues if i.code == "jwt_service_key_fallback_enabled"), None
        )
        assert issue is not None
        assert issue.severity == "warning"
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.allow_service_api_key_in_jwt_mode,
            s.oidc_issuer_url,
            s.oidc_jwks_url,
        ) = snapshot


def test_readiness_prod_sberjazz_requires_strict_connector_policy() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.auth_require_jwt_in_prod,
        s.api_keys,
        s.meeting_connector_provider,
        s.sberjazz_api_base,
        s.sberjazz_api_token,
        s.sberjazz_require_https_in_prod,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "api_key"
        s.auth_require_jwt_in_prod = True
        s.api_keys = "k1"
        s.meeting_connector_provider = "sberjazz"
        s.sberjazz_api_base = "http://sj.example.local"
        s.sberjazz_api_token = ""
        s.sberjazz_require_https_in_prod = True
        state = evaluate_readiness()
        codes = {i.code for i in state.issues}
        assert state.ready is False
        assert "sberjazz_api_token_empty" in codes
        assert "sberjazz_api_base_not_https" in codes
        assert "sberjazz_requires_jwt_auth_mode" in codes
        assert "auth_mode_must_be_jwt_in_prod" in codes
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.auth_require_jwt_in_prod,
            s.api_keys,
            s.meeting_connector_provider,
            s.sberjazz_api_base,
            s.sberjazz_api_token,
            s.sberjazz_require_https_in_prod,
        ) = snapshot


def test_readiness_prod_requires_jwt_by_default() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.auth_require_jwt_in_prod,
        s.api_keys,
        s.storage_mode,
        s.storage_require_shared_in_prod,
        s.cors_allowed_origins,
        s.meeting_connector_provider,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "api_key"
        s.auth_require_jwt_in_prod = True
        s.api_keys = "k1"
        s.storage_mode = "shared_fs"
        s.storage_require_shared_in_prod = True
        s.cors_allowed_origins = "https://example.com"
        s.meeting_connector_provider = "none"
        state = evaluate_readiness()
        codes = {i.code for i in state.issues}
        assert state.ready is False
        assert "auth_mode_must_be_jwt_in_prod" in codes
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.auth_require_jwt_in_prod,
            s.api_keys,
            s.storage_mode,
            s.storage_require_shared_in_prod,
            s.cors_allowed_origins,
            s.meeting_connector_provider,
        ) = snapshot


def test_readiness_prod_can_disable_jwt_requirement() -> None:
    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.auth_require_jwt_in_prod,
        s.api_keys,
        s.storage_mode,
        s.storage_require_shared_in_prod,
        s.cors_allowed_origins,
        s.meeting_connector_provider,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "api_key"
        s.auth_require_jwt_in_prod = False
        s.api_keys = "k1"
        s.storage_mode = "shared_fs"
        s.storage_require_shared_in_prod = True
        s.cors_allowed_origins = "https://example.com"
        s.meeting_connector_provider = "none"
        state = evaluate_readiness()
        codes = {i.code for i in state.issues}
        assert "auth_mode_must_be_jwt_in_prod" not in codes
        assert state.ready is True
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.auth_require_jwt_in_prod,
            s.api_keys,
            s.storage_mode,
            s.storage_require_shared_in_prod,
            s.cors_allowed_origins,
            s.meeting_connector_provider,
        ) = snapshot


def test_startup_readiness_fails_on_sberjazz_probe_when_strict(monkeypatch) -> None:
    class _Health:
        healthy = False

    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.oidc_issuer_url,
        s.oidc_jwks_url,
        s.storage_mode,
        s.cors_allowed_origins,
        s.meeting_connector_provider,
        s.sberjazz_api_base,
        s.sberjazz_api_token,
        s.sberjazz_startup_probe_enabled,
        s.sberjazz_startup_probe_fail_fast_in_prod,
        s.readiness_fail_fast_in_prod,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "jwt"
        s.oidc_jwks_url = "https://issuer.local/jwks"
        s.oidc_issuer_url = None
        s.storage_mode = "shared_fs"
        s.cors_allowed_origins = "https://example.com"
        s.meeting_connector_provider = "sberjazz"
        s.sberjazz_api_base = "https://sj.example.local"
        s.sberjazz_api_token = "token"
        s.sberjazz_startup_probe_enabled = True
        s.sberjazz_startup_probe_fail_fast_in_prod = True
        s.readiness_fail_fast_in_prod = True
        monkeypatch.setattr(
            "interview_analytics_agent.services.readiness_service._get_sberjazz_connector_health",
            lambda: _Health(),
        )
        with pytest.raises(RuntimeError, match="sberjazz_startup_probe_failed"):
            enforce_startup_readiness(service_name="api-gateway")
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.oidc_issuer_url,
            s.oidc_jwks_url,
            s.storage_mode,
            s.cors_allowed_origins,
            s.meeting_connector_provider,
            s.sberjazz_api_base,
            s.sberjazz_api_token,
            s.sberjazz_startup_probe_enabled,
            s.sberjazz_startup_probe_fail_fast_in_prod,
            s.readiness_fail_fast_in_prod,
        ) = snapshot


def test_startup_readiness_warns_on_sberjazz_probe_when_not_strict(monkeypatch) -> None:
    class _Health:
        healthy = False

    s = get_settings()
    snapshot = (
        s.app_env,
        s.auth_mode,
        s.oidc_issuer_url,
        s.oidc_jwks_url,
        s.storage_mode,
        s.cors_allowed_origins,
        s.meeting_connector_provider,
        s.sberjazz_api_base,
        s.sberjazz_api_token,
        s.sberjazz_startup_probe_enabled,
        s.sberjazz_startup_probe_fail_fast_in_prod,
        s.readiness_fail_fast_in_prod,
    )
    try:
        s.app_env = "prod"
        s.auth_mode = "jwt"
        s.oidc_jwks_url = "https://issuer.local/jwks"
        s.oidc_issuer_url = None
        s.storage_mode = "shared_fs"
        s.cors_allowed_origins = "https://example.com"
        s.meeting_connector_provider = "sberjazz"
        s.sberjazz_api_base = "https://sj.example.local"
        s.sberjazz_api_token = "token"
        s.sberjazz_startup_probe_enabled = True
        s.sberjazz_startup_probe_fail_fast_in_prod = False
        s.readiness_fail_fast_in_prod = True
        monkeypatch.setattr(
            "interview_analytics_agent.services.readiness_service._get_sberjazz_connector_health",
            lambda: _Health(),
        )
        state = enforce_startup_readiness(service_name="api-gateway")
        issue = next((i for i in state.issues if i.code == "sberjazz_startup_probe_failed"), None)
        assert issue is not None
        assert issue.severity == "warning"
        assert state.ready is True
    finally:
        (
            s.app_env,
            s.auth_mode,
            s.oidc_issuer_url,
            s.oidc_jwks_url,
            s.storage_mode,
            s.cors_allowed_origins,
            s.meeting_connector_provider,
            s.sberjazz_api_base,
            s.sberjazz_api_token,
            s.sberjazz_startup_probe_enabled,
            s.sberjazz_startup_probe_fail_fast_in_prod,
            s.readiness_fail_fast_in_prod,
        ) = snapshot
