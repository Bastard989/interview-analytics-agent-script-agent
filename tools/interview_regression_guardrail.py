"""
Regression guardrail for objective/comparable interview analytics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Interview analytics regression guardrail")
    p.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/interview_regression",
        help="Directory with regression interview fixtures (*.json)",
    )
    p.add_argument(
        "--report-json",
        default="reports/interview_regression_guardrail.json",
        help="Output JSON report path",
    )
    p.add_argument(
        "--min-score-gap",
        type=float,
        default=0.2,
        help="Minimum expected score gap between strongest and weakest fixture candidate",
    )
    return p.parse_args()


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    from interview_analytics_agent.common.config import get_settings
    from interview_analytics_agent.processing.analytics import build_report
    from interview_analytics_agent.processing.comparison import build_comparison_report

    args = _args()
    fixtures_dir = Path(args.fixtures_dir).resolve()
    if not fixtures_dir.exists():
        print(f"fixtures_dir_not_found: {fixtures_dir}")
        return 2

    files = sorted(p for p in fixtures_dir.glob("*.json") if p.is_file())
    if len(files) < 2:
        print("not_enough_fixtures: need at least 2 fixture json files")
        return 2

    settings = get_settings()
    previous_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    try:
        rows: list[dict[str, Any]] = []
        per_meeting: dict[str, Any] = {}
        for path in files:
            fixture = _load_fixture(path)
            meeting_id = str(fixture.get("meeting_id") or path.stem)
            report = build_report(
                enhanced_transcript=str(fixture.get("enhanced_transcript") or ""),
                meeting_context=dict(fixture.get("context") or {}),
                transcript_segments=list(fixture.get("segments") or []),
            )
            scorecard = report.get("scorecard") or {}
            decision = report.get("decision") or {}
            rows.append(
                {
                    "meeting_id": meeting_id,
                    "report": report,
                    "scorecard": scorecard,
                }
            )
            per_meeting[meeting_id] = {
                "fixture": path.name,
                "overall_score": scorecard.get("overall_score"),
                "overall_confidence": scorecard.get("overall_confidence"),
                "decision": decision.get("decision"),
                "insufficient_evidence_competencies": scorecard.get(
                    "insufficient_evidence_competencies", []
                ),
            }
    finally:
        settings.llm_enabled = previous_llm_enabled

    comparison = build_comparison_report(rows)
    ranking = comparison.get("ranking") or []
    top = ranking[0] if ranking else None
    bottom = ranking[-1] if ranking else None
    top_score = per_meeting.get(top, {}).get("overall_score") if top else None
    bottom_score = per_meeting.get(bottom, {}).get("overall_score") if bottom else None
    score_gap = None
    if top_score is not None and bottom_score is not None:
        score_gap = float(top_score) - float(bottom_score)

    checks = {
        "scorecards_present": {
            "ok": all(v.get("overall_score") is not None for v in per_meeting.values()),
            "details": per_meeting,
        },
        "comparison_has_ranking": {
            "ok": len(ranking) >= 2,
            "ranking": ranking,
        },
        "score_gap_min": {
            "ok": score_gap is not None and score_gap >= float(args.min_score_gap),
            "score_gap": score_gap,
            "threshold": float(args.min_score_gap),
        },
    }

    report = {
        "fixtures_dir": str(fixtures_dir),
        "fixtures": [p.name for p in files],
        "per_meeting": per_meeting,
        "comparison": comparison,
        "checks": checks,
    }
    out_path = Path(args.report_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [name for name, ch in checks.items() if not ch.get("ok")]
    if failed:
        print(f"interview_regression_guardrail_failed: {', '.join(failed)}")
        print(f"report={out_path}")
        return 1

    print("interview_regression_guardrail_ok")
    print(f"report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
