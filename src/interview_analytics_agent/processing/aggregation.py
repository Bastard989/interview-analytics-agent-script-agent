"""
Агрегация сегментов в единый текст и подготовка данных для отчёта.

Назначение:
- собрать enhanced segments в "читаемый" транскрипт
- построить упрощённые таймкоды/структуру (позже расширим)
"""

from __future__ import annotations

from collections.abc import Iterable

from interview_analytics_agent.storage.models import TranscriptSegment


def build_enhanced_transcript(segments: Iterable[TranscriptSegment]) -> str:
    """
    Собирает улучшенный транскрипт в один текст.

    Формат MVP:
    [SPEAKER]: text
    """
    lines: list[str] = []

    for s in segments:
        speaker = s.speaker or "UNKNOWN"
        text = (s.enhanced_text or "").strip()
        if not text:
            continue
        lines.append(f"{speaker}: {text}")

    return "\n".join(lines).strip()
