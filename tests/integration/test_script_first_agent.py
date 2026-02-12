from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEETING_AGENT_SCRIPT = PROJECT_ROOT / "scripts" / "meeting_agent.py"


def _write_fake_quick_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-sec", type=int, default=0)
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--no-local-report", action="store_true")
    parser.add_argument("--stop-flag-path")
    args, _ = parser.parse_known_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    while True:
        if args.duration_sec and (time.monotonic() - started) >= args.duration_sec:
            break
        if args.stop_flag_path and Path(args.stop_flag_path).exists():
            break
        time.sleep(0.05)

    ts = int(time.time() * 1000)
    base = output_dir / f"meeting_{ts}"
    mp3_path = base.with_suffix(".mp3")
    mp3_path.write_bytes(b"ID3FAKE")

    if args.transcribe:
        base.with_suffix(".txt").write_text("transcript line\\n", encoding="utf-8")

    if not args.no_local_report:
        report_json = {
            "summary": "demo summary",
            "bullets": ["b1", "b2"],
            "risk_flags": [],
            "recommendation": "ship",
        }
        base.with_suffix(".report.json").write_text(
            json.dumps(report_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        base.with_suffix(".report.txt").write_text("Summary: demo summary\\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        encoding="utf-8",
    )


def _run_meeting_agent(args: list[str], *, env: dict[str, str], timeout_sec: int = 30) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(MEETING_AGENT_SCRIPT), *args]
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )


def _wait_for_status(output_dir: Path, env: dict[str, str], expected: str, timeout_sec: int = 10) -> str:
    deadline = time.monotonic() + timeout_sec
    last_stdout = ""
    while time.monotonic() < deadline:
        status = _run_meeting_agent(["status", "--output-dir", str(output_dir)], env=env, timeout_sec=10)
        last_stdout = status.stdout
        if f"status: {expected}" in status.stdout:
            return status.stdout
        time.sleep(0.2)
    raise AssertionError(f"Expected status={expected}, got: {last_stdout}")


def _assert_artifacts(output_dir: Path) -> None:
    mp3_files = sorted(output_dir.glob("*.mp3"))
    txt_files = sorted(output_dir.glob("*.txt"))
    report_json_files = sorted(output_dir.glob("*.report.json"))
    report_txt_files = sorted(output_dir.glob("*.report.txt"))

    assert mp3_files, "mp3 artifacts were not created"
    assert txt_files, "txt artifacts were not created"
    assert report_json_files, "report json artifacts were not created"
    assert report_txt_files, "report txt artifacts were not created"

    assert all(path.stat().st_size > 0 for path in mp3_files)
    assert all(path.stat().st_size > 0 for path in txt_files)
    assert all(path.stat().st_size > 0 for path in report_txt_files)
    for report_path in report_json_files:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data.get("summary")


def test_script_first_run_start_status_stop(tmp_path: Path) -> None:
    fake_script = tmp_path / "fake_quick_record.py"
    _write_fake_quick_script(fake_script)

    output_dir = tmp_path / "recordings"
    env = os.environ.copy()
    env["QUICK_RECORD_SCRIPT_PATH"] = str(fake_script)

    run_res = _run_meeting_agent(
        [
            "run",
            "--url",
            "https://meet.example/run",
            "--output-dir",
            str(output_dir),
            "--duration-sec",
            "1",
            "--transcribe",
        ],
        env=env,
        timeout_sec=20,
    )
    assert run_res.returncode == 0, run_res.stderr

    start_res = _run_meeting_agent(
        [
            "start",
            "--url",
            "https://meet.example/bg",
            "--output-dir",
            str(output_dir),
            "--duration-sec",
            "300",
            "--transcribe",
        ],
        env=env,
        timeout_sec=20,
    )
    assert start_res.returncode == 0, start_res.stderr
    assert "started: pid=" in start_res.stdout

    _wait_for_status(output_dir, env, expected="running", timeout_sec=10)

    stop_res = _run_meeting_agent(
        ["stop", "--output-dir", str(output_dir), "--wait-sec", "10"],
        env=env,
        timeout_sec=20,
    )
    assert stop_res.returncode == 0, stop_res.stderr
    assert ("stopped" in stop_res.stdout) or ("stop requested" in stop_res.stdout)

    _wait_for_status(output_dir, env, expected="stopped", timeout_sec=10)
    _assert_artifacts(output_dir)
