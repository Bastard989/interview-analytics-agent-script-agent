"""
Decision engine for hire/hold/no_hire.
"""

from __future__ import annotations

from typing import Any

from interview_analytics_agent.common.config import get_settings


def build_decision_summary(*, scorecard: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    overall_score = scorecard.get("overall_score")
    confidence = float(scorecard.get("overall_confidence") or 0.0)
    insufficient = scorecard.get("insufficient_evidence_competencies") or []
    insufficient_count = len([i for i in insufficient if str(i).strip()])
    risk_flags = report.get("risk_flags") or []
    risk_count = len([i for i in risk_flags if str(i).strip()])

    reasons: list[str] = []
    decision = "hold"

    if overall_score is None:
        decision = "hold"
        reasons.append("overall_score_missing")
    else:
        score = float(overall_score)

        if score <= float(s.decision_nohire_score_max):
            decision = "no_hire"
            reasons.append("score_below_nohire_threshold")
        elif (
            score >= float(s.decision_hire_score_min)
            and confidence >= float(s.decision_min_confidence)
            and insufficient_count <= int(s.decision_max_insufficient_for_hire)
            and risk_count <= int(s.decision_max_risk_for_hire)
        ):
            decision = "hire"
            reasons.append("meets_hire_thresholds")
        elif score < float(s.decision_hold_score_min):
            decision = "no_hire" if risk_count >= int(s.decision_nohire_risk_min) else "hold"
            reasons.append("score_below_hold_threshold")
        else:
            decision = "hold"
            reasons.append("needs_human_review")

    if confidence < float(s.decision_min_confidence):
        reasons.append("confidence_low")
    if insufficient_count > int(s.decision_max_insufficient_for_hire):
        reasons.append("insufficient_evidence")
    if risk_count > int(s.decision_max_risk_for_hire):
        reasons.append("risk_flags_high")

    if decision == "hire":
        next_actions = [
            "Run final senior debrief and compensation alignment.",
            "Verify references and role-specific fit.",
        ]
    elif decision == "hold":
        next_actions = [
            "Schedule focused follow-up interview on weak competencies.",
            "Request at least one additional senior review.",
        ]
    else:
        next_actions = [
            "Close process or consider lower-level role.",
            "Document objective reasons and evidence excerpts.",
        ]

    return {
        "decision": decision,
        "signals": {
            "overall_score": overall_score,
            "overall_confidence": confidence,
            "risk_count": risk_count,
            "insufficient_evidence_count": insufficient_count,
        },
        "thresholds": {
            "hire_score_min": s.decision_hire_score_min,
            "hold_score_min": s.decision_hold_score_min,
            "nohire_score_max": s.decision_nohire_score_max,
            "min_confidence": s.decision_min_confidence,
            "max_insufficient_for_hire": s.decision_max_insufficient_for_hire,
            "max_risk_for_hire": s.decision_max_risk_for_hire,
        },
        "reasons": sorted(set(reasons)),
        "next_actions": next_actions,
        "audience": "senior_interviewers",
    }
