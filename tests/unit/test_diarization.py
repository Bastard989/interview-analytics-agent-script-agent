from __future__ import annotations

from interview_analytics_agent.stt.diarization import resolve_speaker


def test_resolve_speaker_prefers_hint() -> None:
    assert resolve_speaker(hint="Candidate", raw_text="why?", seq=2) == "Candidate"


def test_resolve_speaker_heuristics() -> None:
    assert resolve_speaker(hint=None, raw_text="Interviewer: why this approach?", seq=1) == "Interviewer"
    assert resolve_speaker(hint=None, raw_text="Кандидат: использовал queue", seq=2) == "Candidate"
    assert resolve_speaker(hint=None, raw_text="No explicit role", seq=3) == "Speaker-A"
