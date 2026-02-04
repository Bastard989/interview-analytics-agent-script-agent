from __future__ import annotations

from interview_analytics_agent.stt.base import STTProvider, STTResult


class MockSTTProvider(STTProvider):
    """Заглушка STT: возвращает предсказуемый текст для проверки пайплайна end-to-end."""

    def transcribe_chunk(self, *, audio: bytes, sample_rate: int) -> STTResult:
        return STTResult(text=f"mock_transcript bytes={len(audio)} sr={sample_rate}")
