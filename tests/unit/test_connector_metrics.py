from __future__ import annotations

from types import SimpleNamespace

from interview_analytics_agent.common import metrics
from interview_analytics_agent.storage.blob import StorageHealth


def test_refresh_connector_metrics_sets_gauges(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_analytics_agent.services.sberjazz_service.list_sberjazz_sessions",
        lambda limit=2000: [
            SimpleNamespace(connected=True),
            SimpleNamespace(connected=False),
            SimpleNamespace(connected=True),
        ],
    )
    monkeypatch.setattr(
        "interview_analytics_agent.services.sberjazz_service.get_sberjazz_connector_health",
        lambda: SimpleNamespace(healthy=True),
    )
    monkeypatch.setattr(
        "interview_analytics_agent.services.sberjazz_service.get_sberjazz_circuit_breaker_state",
        lambda: SimpleNamespace(state="closed"),
    )

    metrics.refresh_connector_metrics()

    connected = metrics.SBERJAZZ_SESSIONS_TOTAL.labels(state="connected")._value.get()
    disconnected = metrics.SBERJAZZ_SESSIONS_TOTAL.labels(state="disconnected")._value.get()
    healthy = metrics.SBERJAZZ_CONNECTOR_HEALTH._value.get()
    cb_open = metrics.SBERJAZZ_CIRCUIT_BREAKER_OPEN._value.get()

    assert connected == 2
    assert disconnected == 1
    assert healthy == 1
    assert cb_open == 0


def test_record_reconcile_metrics_sets_last_values() -> None:
    metrics.record_sberjazz_reconcile_result(
        source="job",
        stale=4,
        failed=1,
        reconnected=3,
    )

    stale = metrics.SBERJAZZ_RECONCILE_LAST_STALE._value.get()
    failed = metrics.SBERJAZZ_RECONCILE_LAST_FAILED._value.get()
    reconnected = metrics.SBERJAZZ_RECONCILE_LAST_RECONNECTED._value.get()

    assert stale == 4
    assert failed == 1
    assert reconnected == 3


def test_refresh_storage_metrics_sets_gauge(monkeypatch) -> None:
    monkeypatch.setattr(
        "interview_analytics_agent.storage.blob.check_storage_health_cached",
        lambda max_age_sec=30: StorageHealth(
            mode="shared_fs",
            base_dir="/mnt/nfs/chunks",
            healthy=True,
            error=None,
        ),
    )
    metrics.refresh_storage_metrics()
    assert metrics.STORAGE_HEALTH.labels(mode="shared_fs")._value.get() == 1


def test_record_cb_reset_increments_counter() -> None:
    before = metrics.SBERJAZZ_CIRCUIT_BREAKER_RESETS_TOTAL.labels(
        source="admin",
        reason="manual_reset",
    )._value.get()
    metrics.record_sberjazz_cb_reset(source="admin", reason="manual_reset")
    after = metrics.SBERJAZZ_CIRCUIT_BREAKER_RESETS_TOTAL.labels(
        source="admin",
        reason="manual_reset",
    )._value.get()
    assert after == before + 1


def test_record_live_pull_metrics_sets_last_values() -> None:
    metrics.record_sberjazz_live_pull_result(
        source="job",
        scanned=5,
        connected=3,
        pulled=10,
        ingested=8,
        failed=1,
        invalid_chunks=2,
    )

    assert metrics.SBERJAZZ_LIVE_PULL_LAST_SCANNED._value.get() == 5
    assert metrics.SBERJAZZ_LIVE_PULL_LAST_CONNECTED._value.get() == 3
    assert metrics.SBERJAZZ_LIVE_PULL_LAST_PULLED._value.get() == 10
    assert metrics.SBERJAZZ_LIVE_PULL_LAST_INGESTED._value.get() == 8
    assert metrics.SBERJAZZ_LIVE_PULL_LAST_FAILED._value.get() == 1
    assert metrics.SBERJAZZ_LIVE_PULL_LAST_INVALID_CHUNKS._value.get() == 2
