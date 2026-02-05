"""
E2E smoke: connector live-pull -> internal ingest -> report.

Сценарий:
1) стартуем realtime meeting c auto_join_connector=true
2) триггерим admin live-pull
3) ждём, пока пайплайн соберёт transcript/report
"""

from __future__ import annotations

import argparse
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


def _read_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="E2E smoke: connector live-pull -> internal ingest -> transcript/report"
    )
    p.add_argument("--base-url", default=os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8010"))
    p.add_argument("--user-key", default=os.environ.get("E2E_USER_KEY", "dev-user-key"))
    p.add_argument("--service-key", default=os.environ.get("E2E_SERVICE_KEY", "dev-service-key"))
    p.add_argument(
        "--provider",
        default=os.environ.get("MEETING_CONNECTOR_PROVIDER", "sberjazz_mock"),
        choices=["sberjazz_mock", "sberjazz", "none"],
        help="Connector provider for this smoke run",
    )
    p.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.environ.get("E2E_CONNECTOR_TIMEOUT_SEC", "150")),
        help="Timeout for transcript/report after live-pull start",
    )
    p.add_argument(
        "--require-report",
        action="store_true",
        default=_read_bool("E2E_REQUIRE_REPORT", False),
        help="Require report field (not only transcript) before success",
    )
    p.add_argument(
        "--expect-provider",
        default=os.environ.get("E2E_EXPECT_CONNECTOR_PROVIDER", ""),
        help="Expected connector provider in /meetings/start response",
    )
    return p.parse_args()


def run_live_connector_smoke(
    base_url: str,
    *,
    user_key: str,
    service_key: str,
    timeout_sec: int,
    require_report: bool,
    expect_provider: str,
) -> None:
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
    if not bool(start_data.get("connector_connected")):
        raise RuntimeError("connector_connected expected true after auto-join")
    if expect_provider:
        actual_provider = str(start_data.get("connector_provider") or "")
        if actual_provider != expect_provider:
            raise RuntimeError(
                f"unexpected connector_provider: got={actual_provider}, expected={expect_provider}"
            )

    saw_ingested = False
    deadline = time.time() + max(30, timeout_sec)
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

        status = requests.get(
            f"{base_url}/v1/admin/connectors/sberjazz/{meeting_id}/status",
            headers=_headers(service_key),
            timeout=10,
        )
        status.raise_for_status()
        status_data = status.json()
        if not bool(status_data.get("connected")) and saw_ingested:
            raise RuntimeError("connector disconnected before pipeline finished")
        time.sleep(1.0)

        m = requests.get(
            f"{base_url}/v1/meetings/{meeting_id}",
            headers=_headers(user_key),
            timeout=10,
        )
        m.raise_for_status()
        data = m.json()
        has_transcript = bool(data.get("raw_transcript") or data.get("enhanced_transcript"))
        has_report = data.get("report") is not None
        if has_transcript and saw_ingested and ((not require_report) or has_report):
            return

    target = "report" if require_report else "transcript"
    raise RuntimeError(f"live connector pipeline did not produce {target} in time")


def main() -> int:
    args = _args()
    base_url = args.base_url.rstrip("/")
    user_key = args.user_key
    service_key = args.service_key
    provider = args.provider.strip().lower()
    expect_provider = (args.expect_provider or provider).strip()
    sample_chunk_b64 = os.environ.get("E2E_MOCK_LIVE_CHUNK_B64", "ZTJlLWxpdmUtY2h1bms=")
    if provider == "sberjazz":
        if not (os.environ.get("SBERJAZZ_API_BASE", "") or "").strip():
            print(
                "e2e connector live smoke failed: SBERJAZZ_API_BASE is required for provider=sberjazz"
            )
            return 2
        if not (os.environ.get("SBERJAZZ_API_TOKEN", "") or "").strip():
            print(
                "e2e connector live smoke failed: SBERJAZZ_API_TOKEN is required for provider=sberjazz"
            )
            return 2

    env = dict(os.environ)
    env.update(
        {
            "APP_ENV": env.get("APP_ENV", "dev"),
            "AUTH_MODE": env.get("AUTH_MODE", "api_key"),
            "API_KEYS": env.get("API_KEYS", user_key),
            "SERVICE_API_KEYS": env.get("SERVICE_API_KEYS", service_key),
            "STT_PROVIDER": env.get("STT_PROVIDER", "mock"),
            "LLM_ENABLED": env.get("LLM_ENABLED", "false"),
            "MEETING_CONNECTOR_PROVIDER": provider,
            "MEETING_AUTO_JOIN_ON_START": env.get("MEETING_AUTO_JOIN_ON_START", "true"),
        }
    )
    if provider == "sberjazz_mock":
        env["SBERJAZZ_MOCK_LIVE_CHUNKS_B64"] = env.get(
            "SBERJAZZ_MOCK_LIVE_CHUNKS_B64", sample_chunk_b64
        )

    try:
        subprocess.check_call(["docker", "compose", "up", "-d", "--build"], env=env)
        wait_tcp("127.0.0.1", 8010, timeout_s=120)
        wait_health(base_url, timeout_s=120)
        run_live_connector_smoke(
            base_url,
            user_key=user_key,
            service_key=service_key,
            timeout_sec=args.timeout_sec,
            require_report=args.require_report,
            expect_provider=expect_provider,
        )
    except Exception as e:
        print(f"e2e connector live smoke failed: {e}")
        return 2

    target = "report" if args.require_report else "transcript/report"
    print(f"e2e connector live smoke OK (start -> live-pull -> {target})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
