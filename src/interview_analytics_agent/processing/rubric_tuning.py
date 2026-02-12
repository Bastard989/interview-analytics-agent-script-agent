"""
Adaptive rubric weight tuning from calibration feedback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.time import utc_now_iso


def _path() -> Path:
    s = get_settings()
    return Path(s.scorecard_weight_overrides_path).expanduser().resolve()


def load_weight_overrides() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_weight_overrides(data: dict[str, Any]) -> Path:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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


def _base_weights(scorecard: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in (scorecard.get("competencies") or []):
        cid = str(item.get("competency_id") or "").strip()
        weight = item.get("weight")
        if not cid:
            continue
        try:
            out[cid] = float(weight)
        except Exception:
            out[cid] = 0.0
    total = sum(max(0.0, v) for v in out.values()) or 1.0
    return {k: max(0.0, v) / total for k, v in out.items()}


def _mean_abs_diff_by_competency(
    *,
    agent: dict[str, float],
    reviews: list[dict[str, Any]],
) -> dict[str, float]:
    per_comp: dict[str, list[float]] = {}
    for row in reviews:
        scores = row.get("scores") or {}
        if not isinstance(scores, dict):
            continue
        for cid, agent_score in agent.items():
            if cid not in scores:
                continue
            try:
                diff = abs(float(agent_score) - float(scores[cid]))
            except Exception:
                continue
            per_comp.setdefault(cid, []).append(diff)

    return {
        cid: (sum(vals) / len(vals))
        for cid, vals in per_comp.items()
        if vals
    }


def maybe_update_weights_from_calibration(
    *,
    scorecard: dict[str, Any],
    reviews: list[dict[str, Any]],
) -> dict[str, Any] | None:
    s = get_settings()
    if not s.scorecard_auto_tuning_enabled:
        return None
    if len(reviews) < int(s.scorecard_tuning_min_reviews):
        return None

    base = _base_weights(scorecard)
    agent = _agent_scores(scorecard)
    if not base or not agent:
        return None

    mad = _mean_abs_diff_by_competency(agent=agent, reviews=reviews)
    if not mad:
        return None

    lr = max(0.01, float(s.scorecard_tuning_learning_rate))
    tuned_raw: dict[str, float] = {}
    for cid, base_w in base.items():
        comp_mad = float(mad.get(cid, 0.0))
        reliability = max(0.35, 1.0 - lr * comp_mad)
        tuned_raw[cid] = max(0.01, base_w * reliability)

    total = sum(tuned_raw.values()) or 1.0
    tuned = {cid: round(w / total, 6) for cid, w in tuned_raw.items()}
    position = str(scorecard.get("position_label") or "").strip()

    current = load_weight_overrides()
    by_position = dict(current.get("by_position") or {})
    if position:
        by_position[position] = tuned
    updated = {
        **current,
        "version": "v1",
        "updated_at": utc_now_iso(),
        "global": tuned,
        "by_position": by_position,
        "meta": {
            "source": "calibration_feedback",
            "reviews_count": len(reviews),
            "learning_rate": lr,
            "mean_abs_diff": {k: round(v, 4) for k, v in mad.items()},
        },
    }
    _save_weight_overrides(updated)
    return updated
