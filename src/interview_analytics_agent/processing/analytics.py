"""
Аналитика интервью (MVP).

Задача модуля: собрать итоговый report по улучшенному транскрипту.

Важно:
- При LLM_ENABLED=false модуль обязан работать (fallback) и НЕ импортировать LLM на уровне модуля.
"""

from __future__ import annotations

from typing import Any

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.processing.decision import build_decision_summary
from interview_analytics_agent.processing.scorecard import build_interview_scorecard


def _build_orchestrator():
    """
    Ленивая сборка orchestrator, чтобы сервисы работали без LLM-зависимостей,
    пока LLM выключен.
    """
    s = get_settings()
    if not s.llm_enabled:
        return None

    # импортируем только если LLM реально включён
    from interview_analytics_agent.llm.mock import MockLLMProvider
    from interview_analytics_agent.llm.openai_compat import OpenAICompatProvider
    from interview_analytics_agent.llm.orchestrator import LLMOrchestrator

    # если ключа нет — используем mock
    if not (s.openai_api_key or ""):
        return LLMOrchestrator(MockLLMProvider())

    return LLMOrchestrator(OpenAICompatProvider())


def _with_scorecard(
    *,
    base_report: dict[str, Any],
    enhanced_transcript: str,
    meeting_context: dict[str, Any],
    transcript_segments: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    scorecard = build_interview_scorecard(
        enhanced_transcript=enhanced_transcript,
        meeting_context=meeting_context,
        report=base_report,
        transcript_segments=transcript_segments,
    )
    out = dict(base_report)
    decision = build_decision_summary(scorecard=scorecard, report=out)
    out["scorecard"] = scorecard
    out["decision"] = decision
    if not str(out.get("recommendation") or "").strip():
        if decision["decision"] == "hire":
            out["recommendation"] = "Proceed with hire discussion"
        elif decision["decision"] == "hold":
            out["recommendation"] = "Run targeted follow-up interview"
        else:
            out["recommendation"] = "Do not proceed for this role"
    out["objective_mode"] = True
    out["report_goal"] = "objective_comparable_summary"
    out["report_audience"] = "senior_interviewers"
    return out


def build_report(
    *,
    enhanced_transcript: str,
    meeting_context: dict,
    transcript_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
        fallback = {
            "summary": "LLM disabled; basic report",
            "bullets": [
                "Pipeline OK",
                "LLM enrichment disabled",
            ],
            "risk_flags": [],
            "recommendation": "",
        }
        return _with_scorecard(
            base_report=fallback,
            enhanced_transcript=enhanced_transcript,
            meeting_context=meeting_context,
            transcript_segments=transcript_segments,
        )

    orch = _build_orchestrator()
    if orch is None:
        # на всякий случай: чтобы не падать даже при странной конфигурации
        fallback = {
            "summary": "LLM unavailable; basic report",
            "bullets": ["Pipeline OK", "LLM unavailable"],
            "risk_flags": [],
            "recommendation": "",
        }
        return _with_scorecard(
            base_report=fallback,
            enhanced_transcript=enhanced_transcript,
            meeting_context=meeting_context,
            transcript_segments=transcript_segments,
        )

    system = (
        "Ты аналитик интервью для сеньоров, которые не присутствовали на встрече. "
        "Сделай выводы максимально объективными и сравнимыми между кандидатами: "
        "фиксируй наблюдаемые факты, не добавляй неподтвержденные выводы. "
        "Верни ТОЛЬКО валидный JSON со структурой: "
        "{summary: str, bullets: [str], risk_flags: [str], recommendation: str}."
    )
    user = "Контекст встречи:\n" f"{meeting_context}\n\n" "Транскрипт:\n" f"{enhanced_transcript}\n"

    data = orch.complete_json(system=system, user=user)

    report = {
        "summary": data.get("summary", ""),
        "bullets": data.get("bullets", []) or [],
        "risk_flags": data.get("risk_flags", []) or [],
        "recommendation": data.get("recommendation", ""),
    }
    return _with_scorecard(
        base_report=report,
        enhanced_transcript=enhanced_transcript,
        meeting_context=meeting_context,
        transcript_segments=transcript_segments,
    )
