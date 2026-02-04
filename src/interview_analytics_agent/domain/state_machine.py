"""
Машина состояний пайплайна обработки интервью.

Назначение:
- Централизованное управление переходами стадий
- Предсказуемое поведение при ошибках
- Основа для ретраев и DLQ
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import PipelineStage, PipelineStatus


# =============================================================================
# РЕЗУЛЬТАТ ПЕРЕХОДА
# =============================================================================
@dataclass
class TransitionResult:
    ok: bool
    next_stage: PipelineStage | None = None
    status: PipelineStatus | None = None
    reason: str | None = None


# =============================================================================
# ПОРЯДОК СТАДИЙ
# =============================================================================
def _stage_order() -> list[PipelineStage]:
    return [
        PipelineStage.stt,
        PipelineStage.enhancer,
        PipelineStage.analytics,
        PipelineStage.delivery,
        PipelineStage.retention,
    ]


def next_stage_after(current: PipelineStage) -> PipelineStage | None:
    """
    Возвращает следующую стадию пайплайна.
    """
    order = _stage_order()
    if current not in order:
        return None

    idx = order.index(current)
    return order[idx + 1] if idx + 1 < len(order) else None


# =============================================================================
# ПЕРЕХОД СОСТОЯНИЙ
# =============================================================================
def transition(stage: PipelineStage, status: PipelineStatus) -> TransitionResult:
    """
    Правила перехода:
    - failed  → пайплайн завершён с ошибкой
    - done    → переход к следующей стадии
    - queued / processing → без изменений
    """
    if status == PipelineStatus.failed:
        return TransitionResult(
            ok=False,
            status=PipelineStatus.failed,
            reason="stage_failed",
        )

    if status != PipelineStatus.done:
        return TransitionResult(ok=True, status=status)

    next_stage = next_stage_after(stage)

    if next_stage is None:
        return TransitionResult(ok=True, status=PipelineStatus.done)

    return TransitionResult(
        ok=True,
        status=PipelineStatus.queued,
        next_stage=next_stage,
    )
