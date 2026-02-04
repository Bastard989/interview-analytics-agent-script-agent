"""
Адаптер SberJazz/SaluteJazz.

Назначение:
- подключение к внешней платформе встреч через HTTP API
- базовый join/leave/fetch_recording контракт
"""

from __future__ import annotations

from typing import Any

import requests

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.errors import ErrCode, ProviderError
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.connectors.base import MeetingConnector, MeetingContext

log = get_project_logger()


class SaluteJazzConnector(MeetingConnector):
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout_sec: int | None = None,
    ) -> None:
        s = get_settings()
        self.base_url = (base_url or s.sberjazz_api_base or "").rstrip("/")
        self.api_token = (api_token or s.sberjazz_api_token or "").strip()
        self.timeout_sec = int(timeout_sec if timeout_sec is not None else s.sberjazz_timeout_sec)

    def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict:
        if not self.base_url:
            raise ProviderError(
                ErrCode.CONNECTOR_PROVIDER_ERROR,
                "SBERJAZZ_API_BASE не настроен",
            )

        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                json=payload,
                headers=headers,
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ProviderError(
                ErrCode.CONNECTOR_PROVIDER_ERROR,
                "Ошибка обращения к SberJazz API",
                details={"err": str(e)},
            ) from e

        if not resp.content:
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def join(self, meeting_id: str) -> MeetingContext:
        data = self._request("POST", f"/api/v1/meetings/{meeting_id}/join")
        participants = data.get("participants")
        if not isinstance(participants, list):
            participants = None
        language = str(data.get("language") or "ru")

        log.info("sberjazz_join_ok", extra={"payload": {"meeting_id": meeting_id}})
        return MeetingContext(meeting_id=meeting_id, language=language, participants=participants)

    def leave(self, meeting_id: str) -> None:
        self._request("POST", f"/api/v1/meetings/{meeting_id}/leave")
        log.info("sberjazz_leave_ok", extra={"payload": {"meeting_id": meeting_id}})

    def fetch_recording(self, meeting_id: str):
        data = self._request("GET", f"/api/v1/meetings/{meeting_id}/recording")
        log.info("sberjazz_fetch_recording_ok", extra={"payload": {"meeting_id": meeting_id}})
        return data or None
