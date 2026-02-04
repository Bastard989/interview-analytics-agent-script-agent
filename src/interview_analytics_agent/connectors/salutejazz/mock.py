"""
Mock-коннектор SaluteJazz для dev/тестов.

Назначение:
- позволить гонять пайплайн без реальной платформы встреч
"""

from __future__ import annotations

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.connectors.base import MeetingConnector, MeetingContext


class MockSaluteJazzConnector(MeetingConnector):
    def join(self, meeting_id: str) -> MeetingContext:
        return MeetingContext(
            meeting_id=meeting_id, participants=[{"name": "MockUser", "role": "candidate"}]
        )

    def leave(self, meeting_id: str) -> None:
        return None

    def fetch_recording(self, meeting_id: str):
        return {"type": "audio", "where": "s3://mock", "duration_sec": 0}

    def fetch_live_chunks(
        self, meeting_id: str, *, cursor: str | None = None, limit: int = 20
    ) -> dict | None:
        _ = limit
        s = get_settings()
        sample_b64 = (getattr(s, "sberjazz_mock_live_chunks_b64", "") or "").strip()
        if not sample_b64:
            return {"chunks": [], "next_cursor": cursor}
        if cursor:
            return {"chunks": [], "next_cursor": cursor}
        return {
            "chunks": [{"id": f"{meeting_id}:mock-live:1", "seq": 1, "content_b64": sample_b64}],
            "next_cursor": "mock-live-1",
        }
