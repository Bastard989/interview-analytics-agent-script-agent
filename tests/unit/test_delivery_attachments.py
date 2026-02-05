from __future__ import annotations

from apps.worker_delivery.main import _build_transcript_attachments


def test_build_transcript_attachments() -> None:
    attachments = _build_transcript_attachments(
        raw_text="raw text",
        enhanced_text="enhanced text",
    )
    names = [a[0] for a in attachments]
    assert "raw_transcript.txt" in names
    assert "enhanced_transcript.txt" in names


def test_build_transcript_attachments_skips_empty() -> None:
    attachments = _build_transcript_attachments(
        raw_text="",
        enhanced_text="  ",
    )
    assert attachments == []
