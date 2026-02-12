from __future__ import annotations

import sys
from pathlib import Path

import requests

from interview_analytics_agent.quick_record import (
    QuickRecordConfig,
    build_chunk_payload,
    build_local_report,
    merge_segments_to_wav,
    normalize_agent_base_url,
    run_preflight_checks,
    segment_step_seconds,
    upload_recording_to_agent,
)


class _FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_segment_step_seconds() -> None:
    assert segment_step_seconds(120, 30) == 90


def test_segment_step_seconds_rejects_invalid() -> None:
    for length, overlap in [(0, 0), (10, -1), (10, 10), (10, 15)]:
        try:
            segment_step_seconds(length, overlap)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_normalize_agent_base_url() -> None:
    assert normalize_agent_base_url("http://localhost:8010") == "http://localhost:8010"
    assert normalize_agent_base_url("http://localhost:8010/") == "http://localhost:8010"
    assert normalize_agent_base_url("http://localhost:8010/v1") == "http://localhost:8010"


def test_build_chunk_payload_contains_base64() -> None:
    payload = build_chunk_payload(audio_bytes=b"abc", seq=7, codec="mp3", sample_rate=22050, channels=1)
    assert payload["seq"] == 7
    assert payload["codec"] == "mp3"
    assert payload["sample_rate"] == 22050
    assert payload["channels"] == 1
    assert payload["content_b64"] == "YWJj"


def test_upload_recording_to_agent(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict | None]] = []

    def _fake_request(method, url, json, headers, timeout):
        calls.append((method, url, json))
        if method.upper() == "GET":
            return _FakeResponse(
                {
                    "meeting_id": "quick-123",
                    "status": "completed",
                    "enhanced_transcript": "готово",
                    "report": {"summary": "ok"},
                }
            )
        return _FakeResponse(
            {"ok": True}
        )

    monkeypatch.setattr("interview_analytics_agent.quick_record.requests.request", _fake_request)

    recording = tmp_path / "meeting.mp3"
    recording.write_bytes(b"audio-bytes")

    cfg = QuickRecordConfig(
        meeting_url="https://jazz.sber.ru/meeting/123",
        upload_to_agent=True,
        agent_base_url="http://127.0.0.1:8010/v1",
        agent_api_key="dev-user-key",
        meeting_id="quick-123",
        wait_report_sec=1,
        poll_interval_sec=0.01,
    )

    result = upload_recording_to_agent(recording_path=recording, cfg=cfg)
    assert result.meeting_id == "quick-123"
    assert result.status == "completed"
    assert result.report == {"summary": "ok"}
    assert result.enhanced_transcript == "готово"

    assert calls[0][1] == "http://127.0.0.1:8010/v1/meetings/start"
    assert calls[1][1] == "http://127.0.0.1:8010/v1/meetings/quick-123/chunks"
    assert calls[2][1] == "http://127.0.0.1:8010/v1/meetings/quick-123"


def test_build_local_report_writes_json_and_text(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "interview_analytics_agent.quick_record.build_report",
        lambda **kwargs: {
            "summary": f"ok:{kwargs['meeting_context']['meeting_url']}",
            "bullets": ["b1", "b2"],
            "risk_flags": [],
            "recommendation": "ship",
        },
    )

    cfg = QuickRecordConfig(meeting_url="https://jazz.sber.ru/meeting/777")
    json_path = tmp_path / "report.json"
    txt_path = tmp_path / "report.txt"
    out_json, out_txt = build_local_report(
        transcript_text="test transcript",
        cfg=cfg,
        output_json_path=json_path,
        output_txt_path=txt_path,
    )

    assert out_json == json_path
    assert out_txt == txt_path
    assert "\"summary\": \"ok:https://jazz.sber.ru/meeting/777\"" in json_path.read_text(encoding="utf-8")
    assert "Summary: ok:https://jazz.sber.ru/meeting/777" in txt_path.read_text(encoding="utf-8")


def test_upload_recording_to_agent_retries_transient_errors(monkeypatch, tmp_path: Path) -> None:
    attempts = {"count": 0}

    def _fake_request(method, url, json, headers, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise requests.RequestException("temporary network issue")
        if method.upper() == "GET":
            return _FakeResponse(
                {
                    "meeting_id": "quick-123",
                    "status": "completed",
                    "enhanced_transcript": "готово",
                    "report": {"summary": "ok"},
                }
            )
        return _FakeResponse({"ok": True})

    monkeypatch.setattr("interview_analytics_agent.quick_record.requests.request", _fake_request)

    recording = tmp_path / "meeting.mp3"
    recording.write_bytes(b"audio-bytes")
    cfg = QuickRecordConfig(
        meeting_url="https://jazz.sber.ru/meeting/123",
        upload_to_agent=True,
        agent_base_url="http://127.0.0.1:8010",
        agent_api_key="dev-user-key",
        meeting_id="quick-123",
        agent_http_retries=2,
        agent_http_backoff_sec=0.0,
        wait_report_sec=1,
        poll_interval_sec=0.01,
    )

    result = upload_recording_to_agent(recording_path=recording, cfg=cfg)
    assert result.status == "completed"
    assert attempts["count"] >= 3


def test_run_preflight_checks(monkeypatch, tmp_path: Path) -> None:
    class _Mic:
        def __init__(self, name: str, is_loopback: bool = False) -> None:
            self.name = name
            self.is_loopback = is_loopback

    class _SC:
        @staticmethod
        def all_microphones():
            return [_Mic("Built-in"), _Mic("BlackHole 2ch", True)]

        @staticmethod
        def default_microphone():
            return _Mic("Built-in")

    monkeypatch.setattr("interview_analytics_agent.quick_record.shutil.which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        "interview_analytics_agent.quick_record.shutil.disk_usage",
        lambda _: type("U", (), {"free": 10 * 1024 * 1024 * 1024})(),
    )
    monkeypatch.setitem(sys.modules, "soundcard", _SC)

    cfg = QuickRecordConfig(
        meeting_url="https://jazz.sber.ru/meeting/123",
        output_dir=tmp_path,
        input_device="BlackHole",
        preflight_min_free_mb=100,
    )
    info = run_preflight_checks(cfg)
    assert info["output_dir"] == str(tmp_path)
    assert info["input_device"] == "BlackHole 2ch"


def test_merge_segments_to_wav_skips_overlap(monkeypatch, tmp_path: Path) -> None:
    class _FakeOutFile:
        def __init__(self) -> None:
            self.blocks_written = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, block) -> None:
            self.blocks_written += len(block)

    class _FakeInFile:
        def __init__(self, frames: int) -> None:
            self.samplerate = 10
            self.channels = 1
            self._frames = frames
            self.seek_calls: list[int] = []

        def __len__(self) -> int:
            return self._frames

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def seek(self, frame: int) -> None:
            self.seek_calls.append(frame)

        def blocks(self, blocksize: int = 4096):
            yield [0] * self._frames

    files: dict[str, _FakeInFile | _FakeOutFile] = {}
    seg1 = tmp_path / "seg1.wav"
    seg2 = tmp_path / "seg2.wav"
    seg1.write_bytes(b"x")
    seg2.write_bytes(b"x")
    out_path = tmp_path / "merged.wav"

    def _fake_sound_file(path: str, mode: str, samplerate: int | None = None, channels: int | None = None):
        if mode == "w":
            obj = _FakeOutFile()
            files[path] = obj
            return obj
        if path.endswith("seg1.wav"):
            obj = _FakeInFile(frames=50)
            files[path] = obj
            return obj
        obj = _FakeInFile(frames=50)
        files[path] = obj
        return obj

    monkeypatch.setitem(
        sys.modules,
        "soundfile",
        type("SF", (), {"SoundFile": _fake_sound_file}),
    )

    merge_segments_to_wav(
        segment_paths=[seg1, seg2],
        output_wav=out_path,
        overlap_sec=2,
        remove_sources=False,
    )

    second = files[str(seg2)]
    assert isinstance(second, _FakeInFile)
    assert second.seek_calls == [20]
