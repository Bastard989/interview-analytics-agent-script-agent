"""
Cross-candidate comparison report.
"""

from __future__ import annotations

from typing import Any

from interview_analytics_agent.common.time import utc_now_iso


def _extract_score(row: dict[str, Any], competency_id: str) -> float | None:
    scorecard = row.get("scorecard") or {}
    competencies = scorecard.get("competencies") or []
    for item in competencies:
        if str(item.get("competency_id")) == competency_id:
            val = item.get("score")
            if val is None:
                return None
            try:
                return float(val)
            except Exception:
                return None
    return None


def build_comparison_report(meetings: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    competency_ids: list[str] = []
    for entry in meetings:
        scorecard = entry.get("scorecard") or {}
        report = entry.get("report") or {}
        score = scorecard.get("overall_score")
        confidence = scorecard.get("overall_confidence")
        insufficient = scorecard.get("insufficient_evidence_competencies") or []
        risks = report.get("risk_flags") or []
        rows.append(
            {
                "meeting_id": str(entry.get("meeting_id") or ""),
                "candidate_label": scorecard.get("candidate_label") or None,
                "position_label": scorecard.get("position_label") or None,
                "overall_score": float(score) if score is not None else None,
                "overall_confidence": float(confidence) if confidence is not None else 0.0,
                "risk_count": len([r for r in risks if str(r).strip()]),
                "insufficient_evidence_competencies": insufficient,
            }
        )
        for comp in (scorecard.get("competencies") or []):
            cid = str(comp.get("competency_id") or "").strip()
            if cid and cid not in competency_ids:
                competency_ids.append(cid)

    def _sort_key(item: dict[str, Any]) -> tuple[float, float, float]:
        base = item.get("overall_score")
        return (
            float(base if base is not None else -1.0),
            float(item.get("overall_confidence") or 0.0),
            -float(item.get("risk_count") or 0),
        )

    rows_sorted = sorted(rows, key=_sort_key, reverse=True)
    ranking = [row["meeting_id"] for row in rows_sorted if row["meeting_id"]]

    competency_matrix: list[dict[str, Any]] = []
    for cid in competency_ids:
        points: list[dict[str, Any]] = []
        values: list[float] = []
        for row in meetings:
            mid = str(row.get("meeting_id") or "")
            score = _extract_score(row, cid)
            if score is not None:
                values.append(score)
            points.append({"meeting_id": mid, "score": score})
        spread = (max(values) - min(values)) if values else None
        competency_matrix.append(
            {
                "competency_id": cid,
                "spread": round(float(spread), 2) if spread is not None else None,
                "points": points,
            }
        )

    return {
        "version": "v1",
        "generated_at": utc_now_iso(),
        "report_goal": "objective_comparable_summary",
        "report_audience": "senior_interviewers",
        "meeting_count": len(rows_sorted),
        "ranking": ranking,
        "rows": rows_sorted,
        "competency_matrix": competency_matrix,
        "notes": [
            "Ranking prioritizes overall score, then confidence, then lower risk_count.",
            "Competencies with missing evidence are marked in insufficient_evidence_competencies.",
        ],
    }
