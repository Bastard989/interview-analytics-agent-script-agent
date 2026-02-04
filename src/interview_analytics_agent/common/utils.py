"""
Общие утилиты проекта.

Правила:
- сюда кладём только реально общие функции
- без бизнес-логики
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any


def b64_encode(data: bytes) -> str:
    """
    base64(bytes) -> str
    """
    return base64.b64encode(data).decode("utf-8")


def b64_decode(data_b64: str) -> bytes:
    """
    base64(str) -> bytes
    """
    return base64.b64decode(data_b64.encode("utf-8"))


def sha256_hex(data: bytes) -> str:
    """
    SHA256 для контроля целостности (например, аудио чанков/файлов).
    """
    return hashlib.sha256(data).hexdigest()


def safe_dict(d: dict[str, Any], max_len: int = 500) -> dict[str, Any]:
    """
    Безопасное "обрезание" полей для логов (чтобы не утащить большие тексты).
    """
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > max_len:
            out[k] = v[:max_len] + "...(truncated)"
        else:
            out[k] = v
    return out
