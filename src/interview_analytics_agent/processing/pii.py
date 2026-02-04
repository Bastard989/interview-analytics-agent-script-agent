"""
PII-маскирование (персональные данные).

Важно:
- Это MVP реализация (эвристики/регулярки)
- В проде лучше использовать специализированные решения/модели
- Цель: не отправлять и не хранить чувствительные данные там, где запрещено политикой
"""

from __future__ import annotations

import re

# Примитивные шаблоны (минимум для старта)
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RE_PHONE = re.compile(r"\b(\+?\d[\d\-\s]{7,}\d)\b")
RE_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def mask_pii(text: str) -> str:
    """
    Маскирует наиболее частые PII:
    - email
    - телефон
    - карточные номера (очень грубо)
    """
    if not text:
        return text

    text = RE_EMAIL.sub("[EMAIL]", text)
    text = RE_PHONE.sub("[PHONE]", text)
    text = RE_CARD.sub("[CARD]", text)
    return text
