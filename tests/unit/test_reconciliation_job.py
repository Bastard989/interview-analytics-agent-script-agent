from __future__ import annotations

from types import SimpleNamespace

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.jobs import reconciliation_job


def test_reconciliation_job_skips_when_disabled() -> None:
    s = get_settings()
    snapshot_enabled = s.reconciliation_enabled
    try:
        s.reconciliation_enabled = False
        result = reconciliation_job.run(limit=10)
        assert result is None
    finally:
        s.reconciliation_enabled = snapshot_enabled


def test_reconciliation_job_runs_with_limit(monkeypatch) -> None:
    s = get_settings()
    snapshot_enabled = s.reconciliation_enabled
    snapshot_limit = s.reconciliation_limit
    calls: list[int] = []

    def _fake_reconcile(limit: int):
        calls.append(limit)
        return SimpleNamespace(
            scanned=1,
            stale=1,
            reconnected=1,
            failed=0,
            stale_threshold_sec=900,
            updated_at="2026-02-04T00:00:00+00:00",
        )

    monkeypatch.setattr(reconciliation_job, "reconcile_sberjazz_sessions", _fake_reconcile)
    try:
        s.reconciliation_enabled = True
        s.reconciliation_limit = 123
        result = reconciliation_job.run()
        assert result is not None
        assert calls == [123]
    finally:
        s.reconciliation_enabled = snapshot_enabled
        s.reconciliation_limit = snapshot_limit
