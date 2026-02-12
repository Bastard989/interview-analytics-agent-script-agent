from __future__ import annotations

from interview_analytics_agent.queue.idempotency import check_and_set


def test_check_and_set_inline_mode(monkeypatch) -> None:
    monkeypatch.setattr("interview_analytics_agent.queue.idempotency._settings.queue_mode", "inline")
    assert check_and_set("scope", "m-1", "k-1") is True
    assert check_and_set("scope", "m-1", "k-1") is False
