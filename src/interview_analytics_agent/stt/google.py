"""
Google STT (заглушка).

Реализация будет добавлена позже:
- загрузка credentials из GOOGLE_STT_JSON
- streaming/recognize API
"""

from __future__ import annotations

from .base import STTProvider, STTResult


class GoogleSTTProvider(STTProvider):
    def transcribe_chunk(self, *, audio: bytes, sample_rate: int) -> STTResult:
        return STTResult(text="", confidence=None)
