"""
E2E smoke: connector live-pull -> internal ingest -> report.

Сценарий:
1) стартуем realtime meeting c auto_join_connector=true
2) триггерим admin live-pull
3) ждём, пока пайплайн соберёт transcript/report
"""

from __future__ import annotations

import os
import socket
import subprocess
import time

import requests


def wait_tcp(host: str, port: int, timeout_s: int = 90) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"timeout waiting for {host}:{port}")


def wait_health(base_url: str, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("timeout waiting for /health")


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def run_live_connector_smoke(base_url: str, *, user_key: str, service_key: str) -> None:
    meeting_id = f"e2e-live-{int(time.time())}"
    start_payload = {
        "meeting_id": meeting_id,
        "mode": "realtime",
        "language": "ru",
        "consent": "unknown",
        "context": {"source": "e2e-live"},
        "auto_join_connector": True,
        "recipients": [],
    }
    start = requests.post(
        f"{base_url}/v1/meetings/start",
        json=start_payload,
        headers=_headers(user_key),
        timeout=10,
    )
    start.raise_for_status()
    start_data = start.json()
    if not start_data.get("connector_auto_join"):
        raise RuntimeError("connector_auto_join expected true")

    saw_ingested = False
    deadline = time.time() + 150
    while time.time() < deadline:
        lp = requests.post(
            f"{base_url}/v1/admin/connectors/sberjazz/live-pull?limit_sessions=50&batch_limit=20",
            headers=_headers(service_key),
            timeout=10,
        )
        lp.raise_for_status()
        lp_data = lp.json()
        if int(lp_data.get("ingested", 0)) > 0:
            saw_ingested = True
        time.sleep(1.0)

        m = requests.get(
            f"{base_url}/v1/meetings/{meeting_id}",
            headers=_headers(user_key),
            timeout=10,
        )
        m.raise_for_status()
        data = m.json()
        if (data.get("raw_transcript") or data.get("enhanced_transcript")) and saw_ingested:
            return

    raise RuntimeError("live connector pipeline did not produce transcript in time")


def main() -> int:
    base_url = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
    user_key = os.environ.get("E2E_USER_KEY", "dev-user-key")
    service_key = os.environ.get("E2E_SERVICE_KEY", "dev-service-key")
    sample_chunk_b64 = os.environ.get("E2E_MOCK_LIVE_CHUNK_B64", "ZTJlLWxpdmUtY2h1bms=")

    env = dict(os.environ)
    env.update(
        {
            "APP_ENV": env.get("APP_ENV", "dev"),
            "AUTH_MODE": env.get("AUTH_MODE", "api_key"),
            "API_KEYS": env.get("API_KEYS", user_key),
            "SERVICE_API_KEYS": env.get("SERVICE_API_KEYS", service_key),
            "STT_PROVIDER": env.get("STT_PROVIDER", "mock"),
            "LLM_ENABLED": env.get("LLM_ENABLED", "false"),
            "MEETING_CONNECTOR_PROVIDER": env.get("MEETING_CONNECTOR_PROVIDER", "sberjazz_mock"),
            "MEETING_AUTO_JOIN_ON_START": env.get("MEETING_AUTO_JOIN_ON_START", "true"),
            "SBERJAZZ_MOCK_LIVE_CHUNKS_B64": env.get(
                "SBERJAZZ_MOCK_LIVE_CHUNKS_B64", sample_chunk_b64
            ),
        }
    )

    try:
        subprocess.check_call(["docker", "compose", "up", "-d", "--build"], env=env)
        wait_tcp("127.0.0.1", 8010, timeout_s=120)
        wait_health(base_url, timeout_s=120)
        run_live_connector_smoke(base_url, user_key=user_key, service_key=service_key)
    except Exception as e:
        print(f"e2e connector live smoke failed: {e}")
        return 2

    print("e2e connector live smoke OK (start -> live-pull -> report)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
