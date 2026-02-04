"""
Аналитика интервью (MVP).

Задача модуля: собрать итоговый report по улучшенному транскрипту.

Важно:
- При LLM_ENABLED=false модуль обязан работать (fallback) и НЕ импортировать LLM на уровне модуля.
"""

from __future__ import annotations

from typing import Any

from interview_analytics_agent.common.config import get_settings


def _build_orchestrator():
    """
    Ленивая сборка orchestrator, чтобы сервисы работали без LLM-зависимостей,
    пока LLM выключен.
    """
    s = get_settings()
    if not s.llm_enabled:
        return None

    # импортируем только если LLM реально включён
    from interview_analytics_agent.llm.orchestrator import LLMOrchestrator
    from interview_analytics_agent.llm.mock import MockLLMProvider
    from interview_analytics_agent.llm.openai_compat import OpenAICompatProvider

    # если ключа нет — используем mock
    if not (s.openai_api_key or ""):
        return LLMOrchestrator(MockLLMProvider())

    return LLMOrchestrator(OpenAICompatProvider())


def build_report(*, enhanced_transcript: str, meeting_context: dict) -> dict[str, Any]:
    """
    Сборка отчёта по интервью.

    Возвращаемый формат (MVP):
    - summary: str
    - bullets: list[str]
    - risk_flags: list[str]
    - recommendation: str
    """

    s = get_settings()

    # Fallback: LLM выключен -> простой отчёт, но пайплайн живой
    if not s.llm_enabled:
        return {
            "summary": "LLM disabled; basic report",
            "bullets": [
                "Pipeline OK",
                "LLM enrichment disabled",
            ],
            "risk_flags": [],
            "recommendation": "",
        }

    orch = _build_orchestrator()
    if orch is None:
        # на всякий случай: чтобы не падать даже при странной конфигурации
        return {
            "summary": "LLM unavailable; basic report",
            "bullets": ["Pipeline OK", "LLM unavailable"],
            "risk_flags": [],
            "recommendation": "",
        }

    system = (
        "Ты аналитик интервью. Верни ТОЛЬКО валидный JSON со структурой: "
        "{summary: str, bullets: [str], risk_flags: [str], recommendation: str}."
    )
    user = "Контекст встречи:\n" f"{meeting_context}\n\n" "Транскрипт:\n" f"{enhanced_transcript}\n"

    data = orch.complete_json(system=system, user=user)

    return {
        "summary": data.get("summary", ""),
        "bullets": data.get("bullets", []) or [],
        "risk_flags": data.get("risk_flags", []) or [],
        "recommendation": data.get("recommendation", ""),
    }
