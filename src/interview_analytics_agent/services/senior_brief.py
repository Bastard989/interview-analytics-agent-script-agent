from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from interview_analytics_agent.storage import records


def _first_lines(text: str, max_lines: int = 12) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[:max_lines])


def _competency_lines(scorecard: dict[str, Any], *, max_items: int = 5) -> list[str]:
    rows = scorecard.get("competencies") or []
    ranked = sorted(
        rows,
        key=lambda r: float(r.get("score") or 0.0),
        reverse=True,
    )
    out: list[str] = []
    for item in ranked[:max_items]:
        title = str(item.get("title") or item.get("competency_id") or "")
        score = item.get("score")
        evidence = item.get("evidence") or []
        evidence_quote = ""
        if evidence:
            evidence_quote = str(evidence[0].get("quote") or "")
        out.append(
            f"- {title}: score={score}, evidence={evidence_quote or 'n/a'}"
        )
    return out


def _build_markdown(
    *,
    meeting_id: str,
    report: dict[str, Any],
    enhanced_transcript: str,
) -> str:
    scorecard = report.get("scorecard") or {}
    decision = report.get("decision") or {}
    summary = str(report.get("summary") or "")
    recommendation = str(report.get("recommendation") or "")
    decision_value = str(decision.get("decision") or "hold")
    reasons = decision.get("reasons") or []
    transcript_preview = _first_lines(enhanced_transcript)
    competency_lines = _competency_lines(scorecard)

    lines = [
        f"# Senior Brief: {meeting_id}",
        "",
        f"- Decision: `{decision_value}`",
        f"- Overall score: `{scorecard.get('overall_score')}`",
        f"- Confidence: `{scorecard.get('overall_confidence')}`",
        f"- Reasons: {', '.join(str(r) for r in reasons) if reasons else 'n/a'}",
        "",
        "## Summary",
        summary or "n/a",
        "",
        "## Recommendation",
        recommendation or "n/a",
        "",
        "## Top Competencies (with evidence)",
    ]
    if competency_lines:
        lines.extend(competency_lines)
    else:
        lines.append("- n/a")

    lines.extend(
        [
            "",
            "## Transcript Preview",
            "```",
            transcript_preview or "",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _build_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return (
        "<html><head><meta charset='utf-8'><title>Senior Brief</title></head>"
        "<body><pre style='white-space: pre-wrap; font-family: ui-monospace, monospace;'>"
        f"{escaped}"
        "</pre></body></html>"
    )


def _write_optional_pdf(path: Path, markdown_text: str) -> Path | None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 40
    for line in markdown_text.splitlines():
        if y < 40:
            c.showPage()
            y = height - 40
        c.drawString(40, y, line[:120])
        y -= 14
    c.save()
    return path


def build_senior_brief_artifacts(
    *,
    meeting_id: str,
    report: dict[str, Any],
    enhanced_transcript: str,
) -> dict[str, str | None]:
    md = _build_markdown(
        meeting_id=meeting_id,
        report=report,
        enhanced_transcript=enhanced_transcript,
    )
    txt_path = records.write_text(meeting_id, "senior_brief.txt", md)
    md_path = records.write_text(meeting_id, "senior_brief.md", md)
    html_path = records.write_text(meeting_id, "senior_brief.html", _build_html(md))
    pdf_path = _write_optional_pdf(records.artifact_path(meeting_id, "senior_brief.pdf"), md)
    return {
        "brief_txt_path": str(txt_path),
        "brief_md_path": str(md_path),
        "brief_html_path": str(html_path),
        "brief_pdf_path": str(pdf_path) if pdf_path else None,
    }
