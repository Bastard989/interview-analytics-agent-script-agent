"""
Calibration between agent scorecard and senior reviewers.
"""

from __future__ import annotations

from typing import Any

from interview_analytics_agent.common.time import utc_now_iso


def _agent_scores(scorecard: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in (scorecard.get("competencies") or []):
        cid = str(item.get("competency_id") or "").strip()
        score = item.get("score")
        if not cid or score is None:
            continue
        try:
            out[cid] = float(score)
        except Exception:
            continue
    return out


def _normalize_review_scores(scores: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in (scores or {}).items():
        cid = str(key).strip()
        if not cid:
            continue
        try:
            out[cid] = float(value)
        except Exception:
            continue
    return out


def build_calibration_report(
    *,
    scorecard: dict[str, Any],
    senior_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    agent = _agent_scores(scorecard)
    reviewer_rows: list[dict[str, Any]] = []
    diffs_all: list[float] = []

    for review in senior_reviews:
        reviewer_id = str(review.get("reviewer_id") or "").strip() or "unknown"
        scores = _normalize_review_scores(review.get("scores") or {})

        diffs: dict[str, float] = {}
        for cid, agent_score in agent.items():
            if cid not in scores:
                continue
            diff = abs(agent_score - scores[cid])
            diffs[cid] = round(diff, 2)
            diffs_all.append(diff)

        mad = round(sum(diffs.values()) / len(diffs), 2) if diffs else None
        reviewer_rows.append(
            {
                "reviewer_id": reviewer_id,
                "created_at": review.get("created_at"),
                "decision": review.get("decision"),
                "notes": review.get("notes"),
                "matched_competencies": sorted(diffs.keys()),
                "mean_abs_diff": mad,
                "diff_by_competency": diffs,
            }
        )

    global_mad = round(sum(diffs_all) / len(diffs_all), 2) if diffs_all else None
    if global_mad is None:
        drift_level = "not_enough_data"
    elif global_mad <= 0.5:
        drift_level = "low"
    elif global_mad <= 1.0:
        drift_level = "medium"
    else:
        drift_level = "high"

    return {
        "version": "v1",
        "generated_at": utc_now_iso(),
        "agent_overall_score": scorecard.get("overall_score"),
        "review_count": len(reviewer_rows),
        "global_mean_abs_diff": global_mad,
        "drift_level": drift_level,
        "reviewers": reviewer_rows,
        "notes": [
            "Calibration compares agent competency scores with senior reviewer scores.",
            "Use high drift as signal to refine rubric weights or evidence extraction.",
        ],
    }
