from __future__ import annotations

from interview_analytics_agent.processing.aggregation import (
    build_enhanced_transcript,
    build_raw_transcript,
)
from interview_analytics_agent.storage.models import TranscriptSegment


def test_build_raw_and_enhanced_transcripts() -> None:
    segs = [
        TranscriptSegment(
            meeting_id="m-1",
            seq=1,
            speaker="SPK1",
            raw_text="raw one",
            enhanced_text="enh one",
            confidence=0.9,
        ),
        TranscriptSegment(
            meeting_id="m-1",
            seq=2,
            speaker=None,
            raw_text="raw two",
            enhanced_text="enh two",
            confidence=0.8,
        ),
    ]

    raw = build_raw_transcript(segs)
    enhanced = build_enhanced_transcript(segs)

    assert "SPK1: raw one" in raw
    assert "UNKNOWN: raw two" in raw
    assert "SPK1: enh one" in enhanced
    assert "UNKNOWN: enh two" in enhanced
