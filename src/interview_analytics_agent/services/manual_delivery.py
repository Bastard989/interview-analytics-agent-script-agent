from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from interview_analytics_agent.common.time import utc_now_iso
from interview_analytics_agent.storage import records

_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

_ARTIFACT_NAME_MAP = {
    "raw_txt": "raw.txt",
    "clean_txt": "clean.txt",
    "report_json": "report.json",
    "report_txt": "report.txt",
    "scorecard_json": "scorecard.json",
    "comparison_json": "comparison.json",
    "calibration_json": "calibration_report.json",
}

_ARTIFACT_MIME_MAP = {
    "raw.txt": "text/plain",
    "clean.txt": "text/plain",
    "report.json": "application/json",
    "report.txt": "text/plain",
    "scorecard.json": "application/json",
    "comparison.json": "application/json",
    "calibration_report.json": "application/json",
}


def parse_sender_accounts(*, raw: str, default_email: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if raw.strip():
        for item in raw.split(","):
            token = item.strip()
            if not token:
                continue
            account_id, _, from_email = token.partition(":")
            aid = account_id.strip()
            email = from_email.strip()
            if not aid:
                continue
            entries.append(
                {
                    "account_id": aid,
                    "from_email": email or default_email,
                }
            )

    if not entries:
        entries.append({"account_id": "default", "from_email": default_email})
    return entries


def select_sender_account(
    *,
    accounts: list[dict[str, str]],
    sender_account_id: str | None,
) -> dict[str, str]:
    if not sender_account_id:
        return accounts[0]
    needle = sender_account_id.strip()
    for item in accounts:
        if item["account_id"] == needle:
            return item
    available = ", ".join(a["account_id"] for a in accounts)
    raise ValueError(f"Unknown sender_account '{needle}'. Available: {available}")


def validate_recipients(*, recipients: list[str], max_recipients: int) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for email in recipients:
        addr = (email or "").strip().lower()
        if not addr or addr in seen:
            continue
        if not _RE_EMAIL.match(addr):
            raise ValueError(f"Invalid email: {email}")
        normalized.append(addr)
        seen.add(addr)
    if not normalized:
        raise ValueError("Recipients list is empty")
    if len(normalized) > max_recipients:
        raise ValueError(f"Too many recipients: {len(normalized)} > {max_recipients}")
    return normalized


def build_attachments(
    *,
    meeting_id: str,
    artifact_kinds: list[str],
) -> list[tuple[str, bytes, str]]:
    attachments: list[tuple[str, bytes, str]] = []
    for kind in artifact_kinds:
        mapped_name = _ARTIFACT_NAME_MAP.get(kind)
        if not mapped_name:
            continue
        try:
            path = records.artifact_path(meeting_id, mapped_name)
        except ValueError:
            continue
        if not path.exists() or not path.is_file():
            continue
        mime = _ARTIFACT_MIME_MAP.get(mapped_name, "application/octet-stream")
        attachments.append((mapped_name, path.read_bytes(), mime))
    return attachments


def append_delivery_log(
    *,
    meeting_id: str,
    payload: dict[str, Any],
) -> Path:
    dst = records.artifact_path(meeting_id, "delivery_manual_log.jsonl")
    dst.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": utc_now_iso(),
            **payload,
        },
        ensure_ascii=False,
    )
    with dst.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return dst
