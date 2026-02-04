"""
Улучшение текста (enhancer).

Назначение:
- пунктуация/нормализация
- удаление "ээ/мм" и мусора
- приведение терминов (в будущем)
- (опционально) PII маскирование

На старте: простые эвристики + возможность подключить LLM позже.
"""

from __future__ import annotations

import re

from interview_analytics_agent.common.config import get_settings

from .pii import mask_pii

FILLER_RE = re.compile(r"\b(ээ+|мм+|ну+|типа|как бы|в общем|короче)\b", re.IGNORECASE)
MULTISPACE_RE = re.compile(r"\s+")


def enhance_text(raw_text: str) -> tuple[str, dict]:
    """
    Возвращает:
    - улучшенный текст
    - метаданные преобразований (для трассировки)
    """
    settings = get_settings()
    meta: dict = {"applied": []}

    if not raw_text:
        return raw_text, meta

    text = raw_text

    # 1) удаляем слова-паразиты
    text2 = FILLER_RE.sub("", text)
    if text2 != text:
        meta["applied"].append("filler_cleanup")
        text = text2

    # 2) нормализуем пробелы
    text2 = MULTISPACE_RE.sub(" ", text).strip()
    if text2 != text:
        meta["applied"].append("whitespace_normalize")
        text = text2

    # 3) простейшая "псевдо-пунктуация" (MVP):
    # если нет точки в конце — добавим.
    if text and text[-1] not in ".!?":
        text += "."
        meta["applied"].append("final_punct")

    # 4) PII маскирование по политике
    if settings.pii_masking:
        masked = mask_pii(text)
        if masked != text:
            meta["applied"].append("pii_mask")
            text = masked

    return text, meta
