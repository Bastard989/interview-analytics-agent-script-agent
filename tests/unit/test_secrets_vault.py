from __future__ import annotations

import os

import pytest

from interview_analytics_agent.common.secrets import maybe_load_external_secrets


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict:
        return self._payload


def test_vault_loads_fields(monkeypatch) -> None:
    monkeypatch.setenv("SECRETS_PROVIDER", "vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.local")
    monkeypatch.setenv("VAULT_TOKEN", "tkn")
    monkeypatch.setenv("VAULT_KV_MOUNT", "secret")
    monkeypatch.setenv("VAULT_SECRET_PATH", "agent")
    monkeypatch.setenv("VAULT_FIELD_MAP", "API_KEYS=api_keys,SERVICE_API_KEYS=service_api_keys")

    def _fake_get(*_args, **_kwargs):
        return _FakeResponse(
            {"data": {"data": {"api_keys": "user-1", "service_api_keys": "svc-1"}}}
        )

    monkeypatch.setattr("interview_analytics_agent.common.secrets.requests.get", _fake_get)
    maybe_load_external_secrets()
    assert os.environ.get("API_KEYS") == "user-1"
    assert os.environ.get("SERVICE_API_KEYS") == "svc-1"


def test_vault_does_not_override_existing(monkeypatch) -> None:
    monkeypatch.setenv("SECRETS_PROVIDER", "vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.local")
    monkeypatch.setenv("VAULT_TOKEN", "tkn")
    monkeypatch.setenv("VAULT_KV_MOUNT", "secret")
    monkeypatch.setenv("VAULT_SECRET_PATH", "agent")
    monkeypatch.setenv("VAULT_FIELD_MAP", "API_KEYS=api_keys")
    monkeypatch.setenv("API_KEYS", "existing")

    def _fake_get(*_args, **_kwargs):
        return _FakeResponse({"data": {"data": {"api_keys": "new"}}})

    monkeypatch.setattr("interview_analytics_agent.common.secrets.requests.get", _fake_get)
    maybe_load_external_secrets()
    assert os.environ.get("API_KEYS") == "existing"


def test_vault_missing_env_raises(monkeypatch) -> None:
    monkeypatch.setenv("SECRETS_PROVIDER", "vault")
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_SECRET_PATH", raising=False)

    with pytest.raises(RuntimeError):
        maybe_load_external_secrets()
