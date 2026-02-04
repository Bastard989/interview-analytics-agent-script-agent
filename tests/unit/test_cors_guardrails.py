from __future__ import annotations

import pytest

from apps.api_gateway.main import _cors_params
from interview_analytics_agent.common.config import get_settings


@pytest.fixture()
def cors_settings():
    s = get_settings()
    keys = ["app_env", "cors_allowed_origins", "cors_allow_credentials"]
    snapshot = {k: getattr(s, k) for k in keys}
    try:
        yield s
    finally:
        for k, v in snapshot.items():
            setattr(s, k, v)


def test_prod_rejects_wildcard_origin(cors_settings) -> None:
    cors_settings.app_env = "prod"
    cors_settings.cors_allowed_origins = "*"
    cors_settings.cors_allow_credentials = True

    with pytest.raises(RuntimeError):
        _cors_params()


def test_wildcard_disables_credentials(cors_settings) -> None:
    cors_settings.app_env = "dev"
    cors_settings.cors_allowed_origins = "*"
    cors_settings.cors_allow_credentials = True

    origins, allow_credentials = _cors_params()
    assert origins == ["*"]
    assert allow_credentials is False


def test_csv_origins_keep_credentials(cors_settings) -> None:
    cors_settings.app_env = "prod"
    cors_settings.cors_allowed_origins = "https://app.company.ru,https://admin.company.ru"
    cors_settings.cors_allow_credentials = True

    origins, allow_credentials = _cors_params()
    assert origins == ["https://app.company.ru", "https://admin.company.ru"]
    assert allow_credentials is True
