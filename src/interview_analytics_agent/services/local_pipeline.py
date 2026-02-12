from __future__ import annotations

import threading
from typing import Any

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.domain.enums import PipelineStatus
from interview_analytics_agent.processing.aggregation import (
    build_enhanced_transcript,
    build_raw_transcript,
)
from interview_analytics_agent.processing.analytics import build_report
from interview_analytics_agent.processing.enhancer import enhance_text
from interview_analytics_agent.processing.quality import quality_score
from interview_analytics_agent.storage import records
from interview_analytics_agent.storage.blob import get_bytes
from interview_analytics_agent.storage.db import db_session
from interview_analytics_agent.storage.models import TranscriptSegment
from interview_analytics_agent.storage.repositories import (
    MeetingRepository,
    TranscriptSegmentRepository,
)
from interview_analytics_agent.stt.diarization import resolve_speaker
from interview_analytics_agent.stt.mock import MockSTTProvider

log = get_project_logger()
_stt_provider: Any | None = None
_stt_warmup_started = False
_stt_warmup_lock = threading.Lock()


def _report_to_text(report: dict[str, Any]) -> str:
    bullets = report.get("bullets") or []
    risks = report.get("risk_flags") or []
    lines = [
        f"Summary: {report.get('summary', '')}",
        "",
        "Bullets:",
    ]
    for item in bullets:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Risk Flags:")
    for item in risks:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(f"Recommendation: {report.get('recommendation', '')}")
    return "\n".join(lines).strip() + "\n"


def _build_stt_provider():
    s = get_settings()
    provider = (s.stt_provider or "").strip().lower()

    if provider == "mock":
        return MockSTTProvider()
    if provider == "google":
        from interview_analytics_agent.stt.google import GoogleSTTProvider

        return GoogleSTTProvider()
    if provider == "salutespeech":
        from interview_analytics_agent.stt.salutespeech import SaluteSpeechProvider

        return SaluteSpeechProvider()

    from interview_analytics_agent.stt.whisper_local import WhisperLocalProvider

    return WhisperLocalProvider(
        model_size=s.whisper_model_size,
        device=s.whisper_device,
        compute_type=s.whisper_compute_type,
        language=s.whisper_language,
        vad_filter=s.whisper_vad_filter,
        beam_size=s.whisper_beam_size,
    )


def _get_stt_provider():
    global _stt_provider
    if _stt_provider is None:
        _stt_provider = _build_stt_provider()
    return _stt_provider


def warmup_stt_provider_async() -> None:
    global _stt_warmup_started
    with _stt_warmup_lock:
        if _stt_warmup_started:
            return
        _stt_warmup_started = True

    def _worker() -> None:
        try:
            _get_stt_provider()
            log.info("stt_warmup_ready")
        except Exception as e:
            log.warning("stt_warmup_failed", extra={"payload": {"err": str(e)[:200]}})

    threading.Thread(target=_worker, name="stt-warmup", daemon=True).start()


def process_chunk_inline(
    *,
    meeting_id: str,
    chunk_seq: int,
    audio_bytes: bytes | None = None,
    blob_key: str | None = None,
) -> list[dict[str, Any]]:
    if audio_bytes is None:
        if not blob_key:
            raise ValueError("audio_bytes or blob_key required")
        audio_bytes = get_bytes(blob_key)

    stt = _get_stt_provider()
    stt_result = stt.transcribe_chunk(audio=audio_bytes, sample_rate=16000)
    speaker = resolve_speaker(hint=stt_result.speaker, raw_text=stt_result.text, seq=chunk_seq)
    raw_text = (stt_result.text or "").strip()
    enhanced_text, meta = enhance_text(raw_text)
    q_score = quality_score(raw_text, enhanced_text)

    with db_session() as session:
        mrepo = MeetingRepository(session)
        srepo = TranscriptSegmentRepository(session)
        meeting = mrepo.ensure(meeting_id=meeting_id, meeting_context={"source": "inline_pipeline"})

        if raw_text:
            seg = TranscriptSegment(
                meeting_id=meeting_id,
                seq=chunk_seq,
                speaker=speaker,
                start_ms=None,
                end_ms=None,
                raw_text=raw_text,
                enhanced_text=enhanced_text,
                confidence=stt_result.confidence,
            )
            srepo.upsert_by_meeting_seq(seg)

        segs = srepo.list_by_meeting(meeting_id)
        raw = build_raw_transcript(segs)
        enhanced = build_enhanced_transcript(segs)
        seg_payload = [
            {
                "seq": seg.seq,
                "speaker": seg.speaker,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "raw_text": seg.raw_text,
                "enhanced_text": seg.enhanced_text,
            }
            for seg in segs
        ]
        report = build_report(
            enhanced_transcript=enhanced,
            meeting_context=meeting.context or {},
            transcript_segments=seg_payload,
        )

        meeting.raw_transcript = raw
        meeting.enhanced_transcript = enhanced
        meeting.report = report
        meeting.status = PipelineStatus.done
        mrepo.save(meeting)

    records.write_text(meeting_id, "raw.txt", raw)
    records.write_text(meeting_id, "clean.txt", enhanced)
    records.write_json(meeting_id, "report.json", report)
    scorecard = report.get("scorecard")
    if isinstance(scorecard, dict):
        records.write_json(meeting_id, "scorecard.json", scorecard)
    records.write_text(meeting_id, "report.txt", _report_to_text(report))

    if not raw_text:
        return []

    return [
        {
            "schema_version": "v1",
            "event_type": "transcript.update",
            "meeting_id": meeting_id,
            "seq": chunk_seq,
            "speaker": speaker,
            "raw_text": raw_text,
            "enhanced_text": enhanced_text,
            "confidence": stt_result.confidence,
            "quality": q_score,
            "meta": meta,
        }
    ]
