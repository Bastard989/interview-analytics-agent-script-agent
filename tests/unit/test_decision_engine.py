from __future__ import annotations

from interview_analytics_agent.processing.decision import build_decision_summary


def _scorecard(score: float | None, conf: float, insufficient: list[str] | None = None) -> dict:
    return {
        "overall_score": score,
        "overall_confidence": conf,
        "insufficient_evidence_competencies": insufficient or [],
    }


def test_decision_hire() -> None:
    out = build_decision_summary(
        scorecard=_scorecard(4.4, 0.72, []),
        report={"risk_flags": []},
    )
    assert out["decision"] == "hire"


def test_decision_hold_when_confidence_low() -> None:
    out = build_decision_summary(
        scorecard=_scorecard(4.4, 0.2, []),
        report={"risk_flags": []},
    )
    assert out["decision"] == "hold"
    assert "confidence_low" in out["reasons"]


def test_decision_nohire_when_score_and_risks_bad() -> None:
    out = build_decision_summary(
        scorecard=_scorecard(2.5, 0.7, ["technical_depth", "system_design"]),
        report={"risk_flags": ["risk1", "risk2", "risk3"]},
    )
    assert out["decision"] == "no_hire"
