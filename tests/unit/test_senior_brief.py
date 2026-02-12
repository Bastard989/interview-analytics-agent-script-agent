from __future__ import annotations

from pathlib import Path

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.services.senior_brief import build_senior_brief_artifacts


def test_build_senior_brief_artifacts(tmp_path: Path) -> None:
    s = get_settings()
    snapshot_records = s.records_dir
    try:
        s.records_dir = str(tmp_path)
        paths = build_senior_brief_artifacts(
            meeting_id="m-brief-1",
            report={
                "summary": "Candidate shows strong system thinking.",
                "recommendation": "Proceed",
                "decision": {"decision": "hire", "reasons": ["meets_hire_thresholds"]},
                "scorecard": {
                    "overall_score": 4.3,
                    "overall_confidence": 0.7,
                    "competencies": [
                        {
                            "title": "System Design",
                            "score": 4.4,
                            "evidence": [{"quote": "Used queue and fallback strategy."}],
                        }
                    ],
                },
            },
            enhanced_transcript="Candidate: Used queue and fallback strategy.",
        )
        assert paths["brief_txt_path"]
        assert paths["brief_html_path"]
        txt = Path(paths["brief_txt_path"] or "")
        html = Path(paths["brief_html_path"] or "")
        assert txt.exists()
        assert html.exists()
    finally:
        s.records_dir = snapshot_records
