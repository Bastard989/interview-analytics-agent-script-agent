"""
Оценка качества текста (MVP).

Назначение:
- выдавать грубую оценку качества улучшения
- пригодится для сигналов "стало лучше/хуже" и мониторинга
"""

from __future__ import annotations


def quality_score(raw_text: str, enhanced_text: str) -> float:
    """
    Простейшая эвристика:
    - если текст стал чуть короче и не пустой → +0.1
    - если добавилась пунктуация → +0.1
    - ограничиваем [0..1]
    """
    if not enhanced_text:
        return 0.0

    score = 0.5

    if raw_text and len(enhanced_text) < len(raw_text):
        score += 0.1

    if enhanced_text and enhanced_text[-1] in ".!?":
        score += 0.1

    return max(0.0, min(1.0, score))
