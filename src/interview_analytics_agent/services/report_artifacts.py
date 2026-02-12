from __future__ import annotations

from typing import Any

from interview_analytics_agent.storage import records

from .senior_brief import build_senior_brief_artifacts


def report_to_text(report: dict[str, Any]) -> str:
    bullets = report.get("bullets") or []
    risks = report.get("risk_flags") or []
    decision = report.get("decision") or {}
    lines = [
        f"Summary: {report.get('summary', '')}",
        f"Recommendation: {report.get('recommendation', '')}",
        f"Decision: {decision.get('decision', '')}",
        "",
        "Bullets:",
    ]
    for item in bullets:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Risk Flags:")
    for item in risks:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Decision Reasons:")
    for item in (decision.get("reasons") or []):
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def write_report_artifacts(
    *,
    meeting_id: str,
    raw_text: str,
    clean_text: str,
    report: dict[str, Any],
) -> dict[str, str | None]:
    raw_path = records.write_text(meeting_id, "raw.txt", raw_text)
    clean_path = records.write_text(meeting_id, "clean.txt", clean_text)
    report_json_path = records.write_json(meeting_id, "report.json", report)
    report_txt_path = records.write_text(meeting_id, "report.txt", report_to_text(report))

    scorecard_path = None
    scorecard = report.get("scorecard")
    if isinstance(scorecard, dict):
        scorecard_path = str(records.write_json(meeting_id, "scorecard.json", scorecard))

    decision_path = None
    decision = report.get("decision")
    if isinstance(decision, dict):
        decision_path = str(records.write_json(meeting_id, "decision.json", decision))

    brief_paths = build_senior_brief_artifacts(
        meeting_id=meeting_id,
        report=report,
        enhanced_transcript=clean_text,
    )

    return {
        "raw_path": str(raw_path),
        "clean_path": str(clean_path),
        "report_json_path": str(report_json_path),
        "report_txt_path": str(report_txt_path),
        "scorecard_json_path": scorecard_path,
        "decision_json_path": decision_path,
        **brief_paths,
    }
