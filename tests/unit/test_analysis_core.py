from __future__ import annotations

import json
from pathlib import Path

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.processing.analytics import build_report
from interview_analytics_agent.processing.calibration import build_calibration_report
from interview_analytics_agent.processing.comparison import build_comparison_report


def _fixture(name: str) -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "interview_regression"
        / f"{name}.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_report_contains_scorecard_and_evidence() -> None:
    sample = _fixture("candidate_alpha")
    settings = get_settings()
    snapshot = settings.llm_enabled
    try:
        settings.llm_enabled = False
        report = build_report(
            enhanced_transcript=sample["enhanced_transcript"],
            meeting_context=sample["context"],
            transcript_segments=sample["segments"],
        )
    finally:
        settings.llm_enabled = snapshot

    scorecard = report.get("scorecard")
    assert isinstance(scorecard, dict)
    assert scorecard.get("overall_score") is not None
    comps = scorecard.get("competencies") or []
    assert comps
    assert any((c.get("evidence") or []) for c in comps)


def test_comparison_ranks_stronger_candidate_higher() -> None:
    settings = get_settings()
    snapshot = settings.llm_enabled
    try:
        settings.llm_enabled = False
        alpha = _fixture("candidate_alpha")
        beta = _fixture("candidate_beta")
        alpha_report = build_report(
            enhanced_transcript=alpha["enhanced_transcript"],
            meeting_context=alpha["context"],
            transcript_segments=alpha["segments"],
        )
        beta_report = build_report(
            enhanced_transcript=beta["enhanced_transcript"],
            meeting_context=beta["context"],
            transcript_segments=beta["segments"],
        )
    finally:
        settings.llm_enabled = snapshot

    comparison = build_comparison_report(
        [
            {"meeting_id": alpha["meeting_id"], "report": alpha_report, "scorecard": alpha_report["scorecard"]},
            {"meeting_id": beta["meeting_id"], "report": beta_report, "scorecard": beta_report["scorecard"]},
        ]
    )
    assert comparison["meeting_count"] == 2
    assert comparison["ranking"][0] == "cand-alpha"


def test_calibration_detects_drift() -> None:
    sample = _fixture("candidate_alpha")
    settings = get_settings()
    snapshot = settings.llm_enabled
    try:
        settings.llm_enabled = False
        report = build_report(
            enhanced_transcript=sample["enhanced_transcript"],
            meeting_context=sample["context"],
            transcript_segments=sample["segments"],
        )
    finally:
        settings.llm_enabled = snapshot

    scorecard = report["scorecard"]
    competencies = scorecard["competencies"]
    review_scores = {}
    for item in competencies:
        cid = item.get("competency_id")
        if item.get("score") is None:
            continue
        review_scores[cid] = max(1.0, float(item["score"]) - 1.2)

    calibration = build_calibration_report(
        scorecard=scorecard,
        senior_reviews=[
            {
                "reviewer_id": "senior-1",
                "scores": review_scores,
                "decision": "hold",
                "notes": "stricter bar",
                "created_at": "2026-02-12T12:00:00Z",
            }
        ],
    )
    assert calibration["review_count"] == 1
    assert calibration["global_mean_abs_diff"] is not None
