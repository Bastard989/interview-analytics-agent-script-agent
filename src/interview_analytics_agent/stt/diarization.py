"""
Diarization (определение говорящего).

MVP:
- используем speaker_hint если пришёл
"""


from __future__ import annotations


def _norm(label: str) -> str:
    return (label or "").strip().lower()


def resolve_speaker(
    *,
    hint: str | None,
    raw_text: str | None = None,
    seq: int | None = None,
) -> str | None:
    normalized = _norm(hint or "")
    if normalized:
        return str(hint).strip()

    text = _norm(raw_text or "")
    if text.startswith(("интервьюер:", "interviewer:")):
        return "Interviewer"
    if text.startswith(("кандидат:", "candidate:")):
        return "Candidate"
    if text.endswith("?") or "почему" in text or "why" in text:
        return "Interviewer"

    seq_num = int(seq or 0)
    if seq_num > 0:
        return "Speaker-A" if seq_num % 2 == 1 else "Speaker-B"
    return None
