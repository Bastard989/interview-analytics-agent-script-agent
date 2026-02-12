#!/usr/bin/env python3
"""Script-first meeting agent wrapper (start/status/stop/run)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUICK_SCRIPT = PROJECT_ROOT / "scripts" / "quick_record_meeting.py"


def _parse_common_options(parser: argparse.ArgumentParser, *, require_url: bool) -> None:
    parser.add_argument("--url", required=require_url, help="Meeting URL (http/https)")
    parser.add_argument("--output-dir", default=os.getenv("QUICK_RECORD_OUTPUT_DIR", "recordings"))
    parser.add_argument(
        "--duration-sec",
        type=int,
        default=(int(os.getenv("QUICK_RECORD_DURATION_SEC", "0")) or None),
    )
    parser.add_argument(
        "--segment-length-sec",
        type=int,
        default=int(os.getenv("QUICK_RECORD_SEGMENT_LENGTH_SEC", "120")),
    )
    parser.add_argument(
        "--overlap-sec",
        type=int,
        default=int(os.getenv("QUICK_RECORD_OVERLAP_SEC", "30")),
    )
    parser.add_argument("--sample-rate", type=int, default=int(os.getenv("QUICK_RECORD_SAMPLE_RATE", "44100")))
    parser.add_argument("--block-size", type=int, default=int(os.getenv("QUICK_RECORD_BLOCK_SIZE", "1024")))
    parser.add_argument("--input-device", default=os.getenv("QUICK_RECORD_INPUT_DEVICE"))
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--language", default=os.getenv("QUICK_RECORD_LANGUAGE", "ru"))
    parser.add_argument("--whisper-model-size", default=os.getenv("QUICK_RECORD_WHISPER_MODEL_SIZE"))
    parser.add_argument("--no-local-report", action="store_true")
    parser.add_argument("--upload-to-agent", action="store_true")
    parser.add_argument("--agent-base-url", default=os.getenv("QUICK_RECORD_AGENT_BASE_URL", "http://127.0.0.1:8010"))
    parser.add_argument("--agent-api-key", default=os.getenv("QUICK_RECORD_AGENT_API_KEY"))
    parser.add_argument("--meeting-id", default=os.getenv("QUICK_RECORD_MEETING_ID"))
    parser.add_argument("--wait-report-sec", type=int, default=int(os.getenv("QUICK_RECORD_WAIT_REPORT_SEC", "180")))
    parser.add_argument("--poll-interval-sec", type=float, default=float(os.getenv("QUICK_RECORD_POLL_INTERVAL_SEC", "3")))
    parser.add_argument(
        "--agent-http-retries",
        type=int,
        default=int(os.getenv("QUICK_RECORD_AGENT_HTTP_RETRIES", "2")),
    )
    parser.add_argument(
        "--agent-http-backoff-sec",
        type=float,
        default=float(os.getenv("QUICK_RECORD_AGENT_HTTP_BACKOFF_SEC", "0.75")),
    )
    parser.add_argument(
        "--preflight-min-free-mb",
        type=int,
        default=int(os.getenv("QUICK_RECORD_MIN_FREE_MB", "512")),
    )
    parser.add_argument(
        "--email-to",
        action="append",
        default=[],
        help="Recipient email (repeat flag or comma-separated list)",
    )


def _runtime_file(output_dir: Path) -> Path:
    return output_dir / ".quick_record_agent.runtime.json"


def _log_file(output_dir: Path) -> Path:
    return output_dir / ".quick_record_agent.log"


def _stop_flag_file(output_dir: Path) -> Path:
    return output_dir / ".quick_record_agent.stop"


def _resolve_quick_script() -> Path:
    override = (os.getenv("QUICK_RECORD_SCRIPT_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return QUICK_SCRIPT


def _load_runtime(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_runtime(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _parse_recipients(raw_values: list[str]) -> list[str]:
    recipients: list[str] = []
    for value in raw_values:
        for part in value.split(","):
            email = part.strip()
            if email:
                recipients.append(email)
    return recipients


def _build_quick_cmd(args: argparse.Namespace) -> list[str]:
    quick_script = _resolve_quick_script()
    stop_flag_path = _stop_flag_file(Path(args.output_dir))
    cmd = [
        sys.executable,
        str(quick_script),
    ]
    if args.url:
        cmd.extend(["--url", args.url])
    if args.output_dir:
        cmd.extend(["--output-dir", args.output_dir])
    if args.duration_sec:
        cmd.extend(["--duration-sec", str(args.duration_sec)])
    cmd.extend(["--segment-length-sec", str(args.segment_length_sec)])
    cmd.extend(["--overlap-sec", str(args.overlap_sec)])
    cmd.extend(["--sample-rate", str(args.sample_rate)])
    cmd.extend(["--block-size", str(args.block_size)])
    if args.input_device:
        cmd.extend(["--input-device", str(args.input_device)])
    cmd.extend(["--language", str(args.language)])
    if args.whisper_model_size:
        cmd.extend(["--whisper-model-size", str(args.whisper_model_size)])
    if args.no_open:
        cmd.append("--no-open")
    if args.transcribe:
        cmd.append("--transcribe")
    if args.no_local_report:
        cmd.append("--no-local-report")
    if args.upload_to_agent:
        cmd.append("--upload-to-agent")
    if args.agent_base_url:
        cmd.extend(["--agent-base-url", str(args.agent_base_url)])
    if args.agent_api_key:
        cmd.extend(["--agent-api-key", str(args.agent_api_key)])
    if args.meeting_id:
        cmd.extend(["--meeting-id", str(args.meeting_id)])
    if args.wait_report_sec:
        cmd.extend(["--wait-report-sec", str(args.wait_report_sec)])
    if args.poll_interval_sec:
        cmd.extend(["--poll-interval-sec", str(args.poll_interval_sec)])
    cmd.extend(["--agent-http-retries", str(args.agent_http_retries)])
    cmd.extend(["--agent-http-backoff-sec", str(args.agent_http_backoff_sec)])
    cmd.extend(["--preflight-min-free-mb", str(args.preflight_min_free_mb)])
    cmd.extend(["--stop-flag-path", str(stop_flag_path)])

    recipients = _parse_recipients(args.email_to)
    for recipient in recipients:
        cmd.extend(["--email-to", recipient])
    return cmd


def _tail(path: Path, max_lines: int = 40) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-max_lines:])


def cmd_run(args: argparse.Namespace) -> int:
    cmd = _build_quick_cmd(args)
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False).returncode


def cmd_start(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    runtime_path = _runtime_file(output_dir)
    log_path = _log_file(output_dir)
    stop_flag_path = _stop_flag_file(output_dir)

    state = _load_runtime(runtime_path)
    pid = int(state.get("pid") or 0)
    if pid and _is_pid_running(pid):
        print(f"already running: pid={pid}")
        return 1

    cmd = _build_quick_cmd(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    stop_flag_path.unlink(missing_ok=True)

    with log_path.open("a", encoding="utf-8") as log_fh:
        log_fh.write(f"\n=== meeting-agent start {datetime.now().isoformat()} ===\n")
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    _save_runtime(
        runtime_path,
        {
            "pid": proc.pid,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "cmd": cmd,
            "log_path": str(log_path),
            "output_dir": str(output_dir),
            "url": args.url,
            "stop_flag_path": str(stop_flag_path),
        },
    )
    print(f"started: pid={proc.pid}")
    print(f"log: {log_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    runtime_path = _runtime_file(output_dir)
    state = _load_runtime(runtime_path)
    if not state:
        print("status: idle")
        return 0

    pid = int(state.get("pid") or 0)
    log_path = Path(str(state.get("log_path") or _log_file(output_dir)))
    running = _is_pid_running(pid)
    print(f"status: {'running' if running else 'stopped'}")
    print(f"pid: {pid}")
    print(f"started_at: {state.get('started_at')}")
    print(f"log: {log_path}")
    if args.verbose:
        tail = _tail(log_path)
        if tail:
            print("--- last log lines ---")
            print(tail)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    runtime_path = _runtime_file(output_dir)
    state = _load_runtime(runtime_path)
    if not state:
        print("not running")
        return 0

    pid = int(state.get("pid") or 0)
    if not _is_pid_running(pid):
        print("already stopped")
        return 0

    stop_flag_raw = str(state.get("stop_flag_path") or _stop_flag_file(output_dir))
    stop_flag_path = Path(stop_flag_raw)
    stop_flag_path.parent.mkdir(parents=True, exist_ok=True)
    stop_flag_path.write_text("stop\n", encoding="utf-8")

    deadline = time.time() + max(1, int(args.wait_sec))
    while time.time() < deadline:
        if not _is_pid_running(pid):
            print("stopped")
            stop_flag_path.unlink(missing_ok=True)
            return 0
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGINT)
    except OSError as exc:
        print(f"failed to stop: {exc}")
        return 1

    deadline = time.time() + max(1, int(args.wait_sec))
    while time.time() < deadline:
        if not _is_pid_running(pid):
            print("stopped")
            stop_flag_path.unlink(missing_ok=True)
            return 0
        time.sleep(0.2)

    with suppress(OSError):
        os.kill(pid, signal.SIGTERM)

    print("stop requested (forced term sent)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Script-first meeting agent orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run recording in foreground")
    _parse_common_options(run_p, require_url=True)
    run_p.set_defaults(func=cmd_run)

    start_p = sub.add_parser("start", help="Run recording in background")
    _parse_common_options(start_p, require_url=True)
    start_p.set_defaults(func=cmd_start)

    status_p = sub.add_parser("status", help="Show status of background recording")
    status_p.add_argument("--output-dir", default=os.getenv("QUICK_RECORD_OUTPUT_DIR", "recordings"))
    status_p.add_argument("--verbose", action="store_true")
    status_p.set_defaults(func=cmd_status)

    stop_p = sub.add_parser("stop", help="Stop background recording")
    stop_p.add_argument("--output-dir", default=os.getenv("QUICK_RECORD_OUTPUT_DIR", "recordings"))
    stop_p.add_argument("--wait-sec", type=int, default=20)
    stop_p.set_defaults(func=cmd_stop)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
