"""
Smoke check for alert-relay metrics endpoint.
"""

from __future__ import annotations

import argparse
import re
import time

import requests


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Alert relay metrics smoke")
    p.add_argument("--relay-url", default="http://localhost:9081", help="Alert relay base URL")
    p.add_argument("--sink-url", default="http://localhost:9080", help="Webhook sink base URL")
    p.add_argument("--timeout-sec", type=int, default=30, help="Wait timeout for delivery")
    return p.parse_args()


def _reset_sink(*, sink_url: str) -> None:
    r = requests.post(f"{sink_url}/reset", timeout=5)
    r.raise_for_status()


def _send_warning(*, relay_url: str) -> None:
    payload = {
        "alerts": [
            {
                "labels": {"alertname": "RelayMetricsSmokeWarning", "severity": "warning"},
                "annotations": {"summary": "Relay metrics smoke warning"},
            }
        ]
    }
    r = requests.post(f"{relay_url}/webhook/warning", json=payload, timeout=5)
    r.raise_for_status()


def _sink_warning_count(*, sink_url: str) -> int:
    r = requests.get(f"{sink_url}/stats", timeout=5)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        return 0
    channels = data.get("channels")
    if not isinstance(channels, dict):
        return 0
    return int(channels.get("warning", 0))


def _load_metrics(*, relay_url: str) -> str:
    r = requests.get(f"{relay_url}/metrics", timeout=5)
    r.raise_for_status()
    return r.text


def _parse_labels(labels_raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in labels_raw.split(","):
        chunk = token.strip()
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        out[key.strip()] = value.strip().strip('"')
    return out


def _extract_forward_ok_warning_target(metrics_text: str) -> float:
    for line in metrics_text.splitlines():
        if not line.startswith("agent_alert_relay_forward_total{"):
            continue
        match = re.match(r"^agent_alert_relay_forward_total\{([^}]*)\}\s+([0-9.]+)$", line.strip())
        if not match:
            continue
        labels = _parse_labels(match.group(1))
        if (
            labels.get("channel") == "warning"
            and labels.get("target") == "target"
            and labels.get("result") == "ok"
        ):
            return float(match.group(2))
    return 0.0


def main() -> int:
    args = _args()
    try:
        before = _extract_forward_ok_warning_target(_load_metrics(relay_url=args.relay_url))
        _reset_sink(sink_url=args.sink_url)
        _send_warning(relay_url=args.relay_url)
    except Exception as e:
        print(f"alert relay metrics smoke FAILED during setup: {e}")
        return 2

    deadline = time.time() + args.timeout_sec
    delivered = False
    while time.time() < deadline:
        try:
            delivered = _sink_warning_count(sink_url=args.sink_url) >= 1
            if delivered:
                break
        except Exception:
            pass
        time.sleep(1)

    if not delivered:
        print("alert relay metrics smoke FAILED: warning route was not delivered to sink in time")
        return 2

    try:
        metrics_text = _load_metrics(relay_url=args.relay_url)
        after = _extract_forward_ok_warning_target(metrics_text)
    except Exception as e:
        print(f"alert relay metrics smoke FAILED during metrics check: {e}")
        return 2

    if after < before + 1:
        print(
            "alert relay metrics smoke FAILED: "
            f"expected forward_total increase for warning target (before={before}, after={after})"
        )
        return 2

    if "agent_alert_relay_forward_attempt_latency_ms_bucket" not in metrics_text:
        print("alert relay metrics smoke FAILED: latency histogram not found in /metrics")
        return 2

    print(
        "alert relay metrics smoke OK: "
        f"warning delivered, forward_total(before={before}, after={after})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
