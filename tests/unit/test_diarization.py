from __future__ import annotations

import interview_analytics_agent.stt.diarization as diarization
from interview_analytics_agent.stt.diarization import resolve_speaker


def test_resolve_speaker_prefers_hint() -> None:
    assert resolve_speaker(hint="Candidate", raw_text="why?", seq=2) == "Candidate"


def test_resolve_speaker_heuristics() -> None:
    assert resolve_speaker(hint=None, raw_text="Interviewer: why this approach?", seq=1) == "Interviewer"
    assert resolve_speaker(hint=None, raw_text="Кандидат: использовал queue", seq=2) == "Candidate"
    assert resolve_speaker(hint=None, raw_text="No explicit role", seq=3) == "Speaker-A"


def test_resolve_speaker_by_embedding(monkeypatch) -> None:
    diarization._STATE.clear()
    emb_a = [1.0, 0.0, 0.0]
    emb_b = [0.0, 1.0, 0.0]
    queue = [emb_a, emb_a, emb_b]

    monkeypatch.setattr(
        "interview_analytics_agent.stt.diarization._decode_audio_embedding",
        lambda _audio: queue.pop(0),
    )

    s1 = resolve_speaker(hint=None, raw_text=None, seq=1, meeting_id="m-d", audio_bytes=b"x")
    s2 = resolve_speaker(hint=None, raw_text=None, seq=2, meeting_id="m-d", audio_bytes=b"x")
    s3 = resolve_speaker(hint=None, raw_text=None, seq=3, meeting_id="m-d", audio_bytes=b"x")
    assert s1 == "Speaker-A"
    assert s2 == "Speaker-A"
    assert s3 == "Speaker-B"
