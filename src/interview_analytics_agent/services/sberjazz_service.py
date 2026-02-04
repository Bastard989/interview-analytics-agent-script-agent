"""
Service layer для SberJazz connector.

Содержит:
- выбор провайдера коннектора (real/mock)
- retry/backoff для join/leave
- in-memory состояние сессии подключения
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.errors import ErrCode, ProviderError
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.connectors.base import MeetingConnector
from interview_analytics_agent.connectors.salutejazz.adapter import SaluteJazzConnector
from interview_analytics_agent.connectors.salutejazz.mock import MockSaluteJazzConnector

log = get_project_logger()


@dataclass
class SberJazzSessionState:
    meeting_id: str
    provider: str
    connected: bool
    attempts: int
    last_error: str | None
    updated_at: str


_SESSIONS: dict[str, SberJazzSessionState] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_connector() -> tuple[str, MeetingConnector]:
    s = get_settings()
    provider = (s.meeting_connector_provider or "sberjazz_mock").strip().lower()
    if provider == "sberjazz":
        return provider, SaluteJazzConnector()
    if provider == "sberjazz_mock":
        return provider, MockSaluteJazzConnector()
    raise ProviderError(
        ErrCode.CONNECTOR_PROVIDER_ERROR,
        f"Неизвестный provider: {provider}",
        details={"allowed": "sberjazz,sberjazz_mock"},
    )


def _retry_config() -> tuple[int, float]:
    s = get_settings()
    attempts = max(1, int(s.sberjazz_retries) + 1)
    backoff_sec = max(0, int(s.sberjazz_retry_backoff_ms)) / 1000.0
    return attempts, backoff_sec


def _save_state(state: SberJazzSessionState) -> SberJazzSessionState:
    _SESSIONS[state.meeting_id] = state
    return state


def get_sberjazz_meeting_state(meeting_id: str) -> SberJazzSessionState:
    state = _SESSIONS.get(meeting_id)
    if state:
        return state
    provider, _ = _resolve_connector()
    return SberJazzSessionState(
        meeting_id=meeting_id,
        provider=provider,
        connected=False,
        attempts=0,
        last_error=None,
        updated_at=_now_iso(),
    )


def join_sberjazz_meeting(meeting_id: str) -> SberJazzSessionState:
    provider, connector = _resolve_connector()
    attempts, backoff_sec = _retry_config()
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            connector.join(meeting_id)
            state = SberJazzSessionState(
                meeting_id=meeting_id,
                provider=provider,
                connected=True,
                attempts=attempt,
                last_error=None,
                updated_at=_now_iso(),
            )
            log.info(
                "sberjazz_join_success",
                extra={"payload": {"meeting_id": meeting_id, "attempt": attempt}},
            )
            return _save_state(state)
        except Exception as e:
            last_error = str(e)[:300]
            log.warning(
                "sberjazz_join_retry",
                extra={
                    "payload": {
                        "meeting_id": meeting_id,
                        "attempt": attempt,
                        "error": last_error,
                    }
                },
            )
            if attempt < attempts and backoff_sec > 0:
                time.sleep(backoff_sec * attempt)

    state = SberJazzSessionState(
        meeting_id=meeting_id,
        provider=provider,
        connected=False,
        attempts=attempts,
        last_error=last_error,
        updated_at=_now_iso(),
    )
    _save_state(state)
    raise ProviderError(
        ErrCode.CONNECTOR_PROVIDER_ERROR,
        "SberJazz join не выполнен после retries",
        details=asdict(state),
    )


def leave_sberjazz_meeting(meeting_id: str) -> SberJazzSessionState:
    provider, connector = _resolve_connector()
    attempts, backoff_sec = _retry_config()
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            connector.leave(meeting_id)
            state = SberJazzSessionState(
                meeting_id=meeting_id,
                provider=provider,
                connected=False,
                attempts=attempt,
                last_error=None,
                updated_at=_now_iso(),
            )
            log.info(
                "sberjazz_leave_success",
                extra={"payload": {"meeting_id": meeting_id, "attempt": attempt}},
            )
            return _save_state(state)
        except Exception as e:
            last_error = str(e)[:300]
            log.warning(
                "sberjazz_leave_retry",
                extra={
                    "payload": {
                        "meeting_id": meeting_id,
                        "attempt": attempt,
                        "error": last_error,
                    }
                },
            )
            if attempt < attempts and backoff_sec > 0:
                time.sleep(backoff_sec * attempt)

    state = SberJazzSessionState(
        meeting_id=meeting_id,
        provider=provider,
        connected=True,
        attempts=attempts,
        last_error=last_error,
        updated_at=_now_iso(),
    )
    _save_state(state)
    raise ProviderError(
        ErrCode.CONNECTOR_PROVIDER_ERROR,
        "SberJazz leave не выполнен после retries",
        details=asdict(state),
    )
