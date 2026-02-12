from __future__ import annotations

import json
from pathlib import Path

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.processing.rubric_tuning import (
    load_weight_overrides,
    maybe_update_weights_from_calibration,
)


def _scorecard() -> dict:
    return {
        "position_label": "Senior Backend",
        "competencies": [
            {"competency_id": "problem_solving", "weight": 0.2, "score": 4.0},
            {"competency_id": "technical_depth", "weight": 0.2, "score": 4.2},
            {"competency_id": "system_design", "weight": 0.15, "score": 4.1},
            {"competency_id": "communication", "weight": 0.15, "score": 3.8},
            {"competency_id": "collaboration", "weight": 0.1, "score": 4.0},
            {"competency_id": "ownership", "weight": 0.1, "score": 3.9},
            {"competency_id": "role_fit", "weight": 0.1, "score": 4.1},
        ]
    }


def test_maybe_update_weights_from_calibration(tmp_path: Path) -> None:
    s = get_settings()
    snapshot = {
        "scorecard_weight_overrides_path": s.scorecard_weight_overrides_path,
        "scorecard_auto_tuning_enabled": s.scorecard_auto_tuning_enabled,
        "scorecard_tuning_min_reviews": s.scorecard_tuning_min_reviews,
    }
    try:
        path = tmp_path / "weights.json"
        s.scorecard_weight_overrides_path = str(path)
        s.scorecard_auto_tuning_enabled = True
        s.scorecard_tuning_min_reviews = 2

        reviews = [
            {"scores": {"problem_solving": 3.5, "technical_depth": 3.7}},
            {"scores": {"problem_solving": 3.6, "technical_depth": 3.8}},
        ]
        updated = maybe_update_weights_from_calibration(scorecard=_scorecard(), reviews=reviews)
        assert updated is not None
        loaded = load_weight_overrides()
        assert "global" in loaded
        assert abs(sum(float(v) for v in loaded["global"].values()) - 1.0) < 1e-6
        assert path.exists()
        json.loads(path.read_text(encoding="utf-8"))
    finally:
        s.scorecard_weight_overrides_path = snapshot["scorecard_weight_overrides_path"]
        s.scorecard_auto_tuning_enabled = snapshot["scorecard_auto_tuning_enabled"]
        s.scorecard_tuning_min_reviews = snapshot["scorecard_tuning_min_reviews"]
