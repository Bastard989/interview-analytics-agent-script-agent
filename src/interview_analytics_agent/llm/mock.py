"""
Mock LLM для тестов и dev.

Назначение:
- Быстро гонять пайплайн без реальных вызовов LLM
- Предсказуемый результат
"""

from __future__ import annotations

import json

from .base import LLMProvider, LLMResult


class MockLLMProvider(LLMProvider):
    def complete_json(self, *, system: str, user: str) -> LLMResult:
        payload = {
            "summary": "mock_summary",
            "bullets": ["mock_point_1", "mock_point_2"],
            "risk_flags": [],
        }
        return LLMResult(
            text=json.dumps(payload, ensure_ascii=False),
            usage={"mock": True},
            latency_ms=1,
            model_id="mock",
        )

    def complete_text(self, *, system: str, user: str) -> LLMResult:
        return LLMResult(text="mock_text", usage={"mock": True}, latency_ms=1, model_id="mock")
