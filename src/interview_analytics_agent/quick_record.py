"""
Quick recorder for video meetings.

Combines script-like usability (one-command recording) with production agent features:
- segmented loopback recording with overlap
- mp3 conversion and optional local whisper transcription
- optional upload into Interview Analytics Agent pipeline
- optional summary email via existing SMTP delivery provider
"""

from __future__ import annotations

import base64
import json
import subprocess
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from interview_analytics_agent.common.logging import get_project_logger
from interview_analytics_agent.delivery.base import DeliveryResult
from interview_analytics_agent.delivery.email.sender import SMTPEmailProvider
from interview_analytics_agent.processing.analytics import build_report

log = get_project_logger()


@dataclass
class QuickRecordConfig:
    meeting_url: str
    output_dir: Path = Path("recordings")
    segment_length_sec: int = 120
    overlap_sec: int = 30
    sample_rate: int = 44100
    block_size: int = 1024
    auto_open_url: bool = True
    max_duration_sec: int | None = None

    transcribe: bool = False
    transcribe_language: str = "ru"
    whisper_model_size: str | None = None

    upload_to_agent: bool = False
    agent_base_url: str = "http://127.0.0.1:8010"
    agent_api_key: str | None = None
    meeting_id: str | None = None
    wait_report_sec: int = 180
    poll_interval_sec: float = 3.0

    email_to: list[str] | None = None
    build_local_report: bool = True
    local_report_context: dict[str, Any] | None = None
    external_stop_event: threading.Event | None = None


@dataclass
class AgentUploadResult:
    meeting_id: str
    status: str
    report: dict[str, Any] | None
    enhanced_transcript: str


@dataclass
class QuickRecordResult:
    mp3_path: Path
    transcript_path: Path | None
    local_report_json_path: Path | None
    local_report_txt_path: Path | None
    agent_upload: AgentUploadResult | None
    email_result: DeliveryResult | None


@dataclass
class QuickRecordJobStatus:
    job_id: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    mp3_path: str | None = None
    transcript_path: str | None = None
    local_report_json_path: str | None = None
    local_report_txt_path: str | None = None
    agent_meeting_id: str | None = None


@dataclass
class _QuickRecordJob:
    job_id: str
    config: QuickRecordConfig
    stop_event: threading.Event
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result: QuickRecordResult | None = None


def segment_step_seconds(segment_length_sec: int, overlap_sec: int) -> int:
    if segment_length_sec <= 0:
        raise ValueError("segment_length_sec must be > 0")
    if overlap_sec < 0:
        raise ValueError("overlap_sec must be >= 0")
    if overlap_sec >= segment_length_sec:
        raise ValueError("overlap_sec must be < segment_length_sec")
    return segment_length_sec - overlap_sec


def normalize_agent_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("agent base url is empty")
    if normalized.endswith("/v1"):
        return normalized[: -len("/v1")]
    return normalized


def build_start_payload(*, meeting_id: str, meeting_url: str, language: str) -> dict[str, Any]:
    return {
        "meeting_id": meeting_id,
        "mode": "postmeeting",
        "language": language,
        "consent": "accepted",
        "context": {
            "source": "quick_record",
            "meeting_url": meeting_url,
        },
    }


def build_chunk_payload(
    *,
    audio_bytes: bytes,
    seq: int = 1,
    codec: str = "mp3",
    sample_rate: int = 44100,
    channels: int = 2,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "content_b64": base64.b64encode(audio_bytes).decode("ascii"),
        "codec": codec,
        "sample_rate": sample_rate,
        "channels": channels,
    }


class SegmentedLoopbackRecorder:
    def __init__(
        self,
        *,
        base_path: Path,
        sample_rate: int,
        block_size: int,
        segment_length_sec: int,
        overlap_sec: int,
    ) -> None:
        self.base_path = base_path
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.segment_length_sec = segment_length_sec
        self.overlap_sec = overlap_sec
        self.step_sec = segment_step_seconds(segment_length_sec, overlap_sec)
        self.stop_event = threading.Event()
        self.segment_paths: list[Path] = []
        self._active: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def _select_loopback(self, sc_module: Any):
        mics = list(sc_module.all_microphones())
        loopback = next((m for m in mics if getattr(m, "is_loopback", False)), None)
        if loopback is None:
            loopback = sc_module.default_microphone()
        if loopback is None:
            raise RuntimeError("No microphone/loopback device available")
        return loopback

    def stop(self) -> None:
        self.stop_event.set()

    def record(self) -> None:
        try:
            try:
                import soundcard as sc
                import soundfile as sf
            except ImportError as exc:
                raise RuntimeError(
                    "quick recorder requires soundcard + soundfile (pip install -r requirements.txt)"
                ) from exc

            loopback = self._select_loopback(sc)
            next_start = 0.0
            index = 0
            started_at = time.monotonic()

            with loopback.recorder(samplerate=self.sample_rate, blocksize=self.block_size) as recorder:
                channels = len(recorder.channelmap)

                while not self.stop_event.is_set():
                    data = recorder.record(numframes=self.block_size)
                    elapsed = time.monotonic() - started_at

                    if elapsed >= next_start:
                        index += 1
                        seg_path = Path(f"{self.base_path}_{index:04d}.wav")
                        handle = sf.SoundFile(
                            str(seg_path),
                            mode="w",
                            samplerate=self.sample_rate,
                            channels=channels,
                        )
                        self._active.append({"start": elapsed, "file": handle})
                        self.segment_paths.append(seg_path)
                        next_start = elapsed + self.step_sec

                    for seg in list(self._active):
                        seg["file"].write(data)
                        if elapsed - float(seg["start"]) >= self.segment_length_sec:
                            seg["file"].close()
                            self._active.remove(seg)
        except Exception as exc:
            self.error = exc
        finally:
            for seg in self._active:
                seg["file"].close()
            self._active.clear()


def merge_segments_to_wav(
    *,
    segment_paths: list[Path],
    output_wav: Path,
    block_size: int = 4096,
    remove_sources: bool = True,
) -> None:
    if not segment_paths:
        raise RuntimeError("No recorded segments found")

    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "Merging segments requires soundfile (pip install -r requirements.txt)"
        ) from exc

    ordered = sorted(segment_paths)
    with sf.SoundFile(str(ordered[0]), mode="r") as first:
        samplerate = int(first.samplerate)
        channels = int(first.channels)

    with sf.SoundFile(str(output_wav), mode="w", samplerate=samplerate, channels=channels) as out:
        for seg_path in ordered:
            with sf.SoundFile(str(seg_path), mode="r") as seg:
                for block in seg.blocks(blocksize=block_size):
                    out.write(block)
            if remove_sources:
                seg_path.unlink(missing_ok=True)


def convert_wav_to_mp3(*, wav_path: Path, mp3_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        str(mp3_path),
    ]
    subprocess.run(cmd, check=True)


def transcribe_with_local_whisper(
    *,
    audio_path: Path,
    language: str,
    model_size: str | None = None,
) -> str:
    from interview_analytics_agent.stt.whisper_local import WhisperLocalProvider

    provider = WhisperLocalProvider(model_size=model_size, language=language)
    audio_bytes = audio_path.read_bytes()
    result = provider.transcribe_chunk(audio=audio_bytes, sample_rate=16000)
    return result.text.strip()


def upload_recording_to_agent(*, recording_path: Path, cfg: QuickRecordConfig) -> AgentUploadResult:
    if not cfg.agent_api_key:
        raise ValueError("agent_api_key is required for upload")

    meeting_id = cfg.meeting_id or f"quick-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    base_url = normalize_agent_base_url(cfg.agent_base_url)
    headers = {
        "X-API-Key": cfg.agent_api_key,
        "Content-Type": "application/json",
    }

    start_payload = build_start_payload(
        meeting_id=meeting_id,
        meeting_url=cfg.meeting_url,
        language=cfg.transcribe_language,
    )
    start_resp = requests.post(
        f"{base_url}/v1/meetings/start",
        json=start_payload,
        headers=headers,
        timeout=20,
    )
    start_resp.raise_for_status()

    chunk_payload = build_chunk_payload(
        audio_bytes=recording_path.read_bytes(),
        seq=1,
        codec="mp3",
        sample_rate=cfg.sample_rate,
        channels=2,
    )
    chunk_resp = requests.post(
        f"{base_url}/v1/meetings/{meeting_id}/chunks",
        json=chunk_payload,
        headers=headers,
        timeout=60,
    )
    chunk_resp.raise_for_status()

    deadline = time.monotonic() + max(1, int(cfg.wait_report_sec))
    last_status = "in_progress"
    last_report: dict[str, Any] | None = None
    last_transcript = ""

    while time.monotonic() < deadline:
        get_resp = requests.get(
            f"{base_url}/v1/meetings/{meeting_id}",
            headers=headers,
            timeout=20,
        )
        get_resp.raise_for_status()
        payload = get_resp.json()
        last_status = str(payload.get("status") or "unknown")
        last_report = payload.get("report")
        last_transcript = str(payload.get("enhanced_transcript") or "")

        if last_report or last_transcript:
            break

        time.sleep(max(0.1, float(cfg.poll_interval_sec)))

    return AgentUploadResult(
        meeting_id=meeting_id,
        status=last_status,
        report=last_report,
        enhanced_transcript=last_transcript,
    )


def send_summary_email(
    *,
    cfg: QuickRecordConfig,
    mp3_path: Path,
    transcript_path: Path | None,
    local_report_json_path: Path | None,
    local_report_txt_path: Path | None,
    upload_result: AgentUploadResult | None,
) -> DeliveryResult | None:
    recipients = [r.strip() for r in (cfg.email_to or []) if r.strip()]
    if not recipients:
        return None

    meeting_id = upload_result.meeting_id if upload_result else (cfg.meeting_id or "quick-record")

    attachments: list[tuple[str, bytes, str]] = [
        (mp3_path.name, mp3_path.read_bytes(), "audio/mpeg"),
    ]
    if transcript_path and transcript_path.exists():
        attachments.append((transcript_path.name, transcript_path.read_bytes(), "text/plain"))
    if local_report_json_path and local_report_json_path.exists():
        attachments.append(
            (
                local_report_json_path.name,
                local_report_json_path.read_bytes(),
                "application/json",
            )
        )
    if local_report_txt_path and local_report_txt_path.exists():
        attachments.append((local_report_txt_path.name, local_report_txt_path.read_bytes(), "text/plain"))

    text_body = (
        f"Recording finished.\n"
        f"Meeting URL: {cfg.meeting_url}\n"
        f"MP3: {mp3_path}\n"
        f"Transcript: {transcript_path or 'not generated'}\n"
        f"Local report (json): {local_report_json_path or 'not generated'}\n"
        f"Local report (txt): {local_report_txt_path or 'not generated'}\n"
        f"Agent meeting id: {meeting_id}\n"
    )

    html_body = (
        "<h3>Quick meeting recording finished</h3>"
        f"<p><b>Meeting URL:</b> {cfg.meeting_url}</p>"
        f"<p><b>MP3:</b> {mp3_path.name}</p>"
        f"<p><b>Transcript:</b> {transcript_path.name if transcript_path else 'not generated'}</p>"
        f"<p><b>Local report JSON:</b> "
        f"{local_report_json_path.name if local_report_json_path else 'not generated'}</p>"
        f"<p><b>Local report TXT:</b> "
        f"{local_report_txt_path.name if local_report_txt_path else 'not generated'}</p>"
        f"<p><b>Agent meeting id:</b> {meeting_id}</p>"
    )

    provider = SMTPEmailProvider()
    return provider.send_report(
        meeting_id=meeting_id,
        recipients=recipients,
        subject=f"Quick recording finished: {meeting_id}",
        html_body=html_body,
        text_body=text_body,
        attachments=attachments,
    )


def _validate_meeting_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        raise ValueError("meeting_url is empty")
    if not (normalized.startswith("http://") or normalized.startswith("https://")):
        raise ValueError("meeting_url must start with http:// or https://")
    return normalized


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


def build_local_report(
    *,
    transcript_text: str,
    cfg: QuickRecordConfig,
    output_json_path: Path,
    output_txt_path: Path,
) -> tuple[Path, Path]:
    context = dict(cfg.local_report_context or {})
    context.setdefault("source", "quick_record_local")
    context.setdefault("meeting_url", cfg.meeting_url)
    context.setdefault("language", cfg.transcribe_language)

    report = build_report(
        enhanced_transcript=transcript_text,
        meeting_context=context,
    )
    output_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_txt_path.write_text(_report_to_text(report), encoding="utf-8")
    return output_json_path, output_txt_path


def _wait_for_stop_or_timeout(
    *,
    recorder: SegmentedLoopbackRecorder,
    stop_event: threading.Event | None,
    max_duration_sec: int | None,
) -> None:
    if max_duration_sec and max_duration_sec > 0:
        deadline = time.monotonic() + max_duration_sec
        while time.monotonic() < deadline:
            if recorder.error is not None:
                break
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(0.2)
        return

    if stop_event is not None:
        while not stop_event.is_set():
            if recorder.error is not None:
                break
            time.sleep(0.2)
        return

    try:
        input("Recording started. Press Enter to stop...\n")
    except EOFError:
        time.sleep(5)


def run_quick_record(cfg: QuickRecordConfig) -> QuickRecordResult:
    cfg.meeting_url = _validate_meeting_url(cfg.meeting_url)
    segment_step_seconds(cfg.segment_length_sec, cfg.overlap_sec)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"meeting_{timestamp}"

    seg_base = cfg.output_dir / base_name
    wav_path = cfg.output_dir / f"{base_name}.wav"
    mp3_path = cfg.output_dir / f"{base_name}.mp3"
    txt_path = cfg.output_dir / f"{base_name}.txt"
    report_json_path = cfg.output_dir / f"{base_name}.report.json"
    report_txt_path = cfg.output_dir / f"{base_name}.report.txt"

    if cfg.auto_open_url:
        webbrowser.open(cfg.meeting_url, new=2)

    recorder = SegmentedLoopbackRecorder(
        base_path=seg_base,
        sample_rate=cfg.sample_rate,
        block_size=cfg.block_size,
        segment_length_sec=cfg.segment_length_sec,
        overlap_sec=cfg.overlap_sec,
    )

    thread = threading.Thread(target=recorder.record, daemon=True)
    thread.start()

    _wait_for_stop_or_timeout(
        recorder=recorder,
        stop_event=cfg.external_stop_event,
        max_duration_sec=cfg.max_duration_sec,
    )

    recorder.stop()
    thread.join(timeout=20)
    if recorder.error is not None:
        raise RuntimeError(f"Recording failed: {recorder.error}") from recorder.error
    if not recorder.segment_paths:
        raise RuntimeError("Recording failed: no audio segments were produced")

    merge_segments_to_wav(segment_paths=recorder.segment_paths, output_wav=wav_path)
    convert_wav_to_mp3(wav_path=wav_path, mp3_path=mp3_path)
    wav_path.unlink(missing_ok=True)

    transcript_path: Path | None = None
    if cfg.transcribe:
        text = transcribe_with_local_whisper(
            audio_path=mp3_path,
            language=cfg.transcribe_language,
            model_size=cfg.whisper_model_size,
        )
        txt_path.write_text(text, encoding="utf-8")
        transcript_path = txt_path

    upload_result: AgentUploadResult | None = None
    if cfg.upload_to_agent:
        upload_result = upload_recording_to_agent(recording_path=mp3_path, cfg=cfg)

    local_report_json_path: Path | None = None
    local_report_txt_path: Path | None = None
    if cfg.build_local_report:
        report_source_text = ""
        if transcript_path and transcript_path.exists():
            report_source_text = transcript_path.read_text(encoding="utf-8").strip()
        elif upload_result and upload_result.enhanced_transcript:
            report_source_text = upload_result.enhanced_transcript.strip()

        if report_source_text:
            local_report_json_path, local_report_txt_path = build_local_report(
                transcript_text=report_source_text,
                cfg=cfg,
                output_json_path=report_json_path,
                output_txt_path=report_txt_path,
            )

    email_result = send_summary_email(
        cfg=cfg,
        mp3_path=mp3_path,
        transcript_path=transcript_path,
        local_report_json_path=local_report_json_path,
        local_report_txt_path=local_report_txt_path,
        upload_result=upload_result,
    )

    log.info(
        "quick_record_done",
        extra={
            "payload": {
                "mp3_path": str(mp3_path),
                "transcript_path": str(transcript_path) if transcript_path else None,
                "local_report_json_path": (
                    str(local_report_json_path) if local_report_json_path else None
                ),
                "local_report_txt_path": (
                    str(local_report_txt_path) if local_report_txt_path else None
                ),
                "uploaded": bool(upload_result),
                "email_sent": bool(email_result and email_result.ok),
            }
        },
    )

    return QuickRecordResult(
        mp3_path=mp3_path,
        transcript_path=transcript_path,
        local_report_json_path=local_report_json_path,
        local_report_txt_path=local_report_txt_path,
        agent_upload=upload_result,
        email_result=email_result,
    )


class QuickRecordManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_job_id: str | None = None
        self._jobs: dict[str, _QuickRecordJob] = {}

    def _as_status(self, job: _QuickRecordJob) -> QuickRecordJobStatus:
        return QuickRecordJobStatus(
            job_id=job.job_id,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error=job.error,
            mp3_path=str(job.result.mp3_path) if job.result else None,
            transcript_path=(
                str(job.result.transcript_path)
                if job.result and job.result.transcript_path
                else None
            ),
            local_report_json_path=(
                str(job.result.local_report_json_path)
                if job.result and job.result.local_report_json_path
                else None
            ),
            local_report_txt_path=(
                str(job.result.local_report_txt_path)
                if job.result and job.result.local_report_txt_path
                else None
            ),
            agent_meeting_id=(
                job.result.agent_upload.meeting_id if job.result and job.result.agent_upload else None
            ),
        )

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        try:
            result = run_quick_record(job.config)
            with self._lock:
                job = self._jobs[job_id]
                job.result = result
                job.status = "completed"
                job.finished_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None

    def start(self, cfg: QuickRecordConfig) -> QuickRecordJobStatus:
        with self._lock:
            if self._active_job_id:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in {"queued", "running", "stopping"}:
                    raise RuntimeError("quick record already running")
                self._active_job_id = None

            job_id = f"qr-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            stop_event = threading.Event()
            cfg.external_stop_event = stop_event
            job = _QuickRecordJob(
                job_id=job_id,
                config=cfg,
                stop_event=stop_event,
                status="queued",
                created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            )
            self._jobs[job_id] = job
            self._active_job_id = job_id

            thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
            thread.start()
            return self._as_status(job)

    def get_status(self, job_id: str | None = None) -> QuickRecordJobStatus | None:
        with self._lock:
            target_id = job_id or self._active_job_id
            if not target_id:
                return None
            job = self._jobs.get(target_id)
            if not job:
                return None
            return self._as_status(job)

    def stop(self) -> QuickRecordJobStatus | None:
        with self._lock:
            if not self._active_job_id:
                return None
            job = self._jobs.get(self._active_job_id)
            if not job:
                self._active_job_id = None
                return None
            if job.status not in {"queued", "running"}:
                return self._as_status(job)
            job.status = "stopping"
            job.stop_event.set()
            return self._as_status(job)


_MANAGER = QuickRecordManager()


def get_quick_record_manager() -> QuickRecordManager:
    return _MANAGER
