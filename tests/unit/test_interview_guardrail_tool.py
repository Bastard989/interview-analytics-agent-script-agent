from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_interview_regression_guardrail_tool(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    script_path = project_root / "tools" / "interview_regression_guardrail.py"
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "interview_regression"
    report_path = tmp_path / "guardrail.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--fixtures-dir",
            str(fixtures_dir),
            "--report-json",
            str(report_path),
            "--min-score-gap",
            "0.1",
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert report_path.exists()
