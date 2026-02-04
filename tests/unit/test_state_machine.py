from interview_analytics_agent.domain.enums import PipelineStage, PipelineStatus
from interview_analytics_agent.domain.state_machine import transition


def test_transition_done_goes_next():
    r = transition(PipelineStage.stt, PipelineStatus.done)
    assert r.ok is True
    assert r.next_stage == PipelineStage.enhancer


def test_transition_failed_stops():
    r = transition(PipelineStage.stt, PipelineStatus.failed)
    assert r.ok is False
    assert r.status == PipelineStatus.failed
