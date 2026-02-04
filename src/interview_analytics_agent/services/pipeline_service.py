"""
Сервисный слой: управление пайплайном обработки.

Назначение:
- постановка задач в очередь по стадиям
- переходы статусов (state_machine)
"""

from __future__ import annotations

from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.domain.enums import PipelineStage, PipelineStatus
from interview_analytics_agent.domain.state_machine import transition
from interview_analytics_agent.queue.dispatcher import (
    enqueue_analytics,
    enqueue_delivery,
    enqueue_enhancer,
    enqueue_retention,
    enqueue_stt,
)

log = get_project_logger()


def enqueue_initial_stt(*, meeting_id: str, chunk_seq: int, blob_key: str) -> str:
    """
    Начало realtime пайплайна: STT на конкретный чанк.
    """
    return enqueue_stt(meeting_id=meeting_id, chunk_seq=chunk_seq, blob_key=blob_key)


def on_stage_finished(*, meeting_id: str, stage: PipelineStage) -> None:
    """
    Реакция на успешное завершение стадии:
    - решаем, какая следующая стадия
    - ставим в соответствующую очередь
    """
    tr = transition(stage, PipelineStatus.done)

    if tr.next_stage is None:
        log.info("pipeline_finished", extra={"meeting_id": meeting_id})
        enqueue_retention(entity_type="meeting", entity_id=meeting_id, reason="pipeline_done")
        return

    if tr.next_stage == PipelineStage.enhancer:
        enqueue_enhancer(meeting_id=meeting_id)
    elif tr.next_stage == PipelineStage.analytics:
        enqueue_analytics(meeting_id=meeting_id)
    elif tr.next_stage == PipelineStage.delivery:
        enqueue_delivery(meeting_id=meeting_id)
    elif tr.next_stage == PipelineStage.retention:
        enqueue_retention(entity_type="meeting", entity_id=meeting_id, reason="pipeline_done")
