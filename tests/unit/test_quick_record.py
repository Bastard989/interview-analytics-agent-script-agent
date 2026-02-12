from __future__ import annotations

from pathlib import Path

from interview_analytics_agent.quick_record import (
    QuickRecordConfig,
    build_chunk_payload,
    build_local_report,
    normalize_agent_base_url,
    segment_step_seconds,
    upload_recording_to_agent,
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

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
    calls: dict[str, list[tuple[str, dict]]] = {"post": [], "get": []}

    def _fake_post(url, json, headers, timeout):
        calls["post"].append((url, json))
        return _FakeResponse({"ok": True})

    def _fake_get(url, headers, timeout):
        calls["get"].append((url, {}))
        return _FakeResponse(
            {
                "meeting_id": "quick-123",
                "status": "completed",
                "enhanced_transcript": "готово",
                "report": {"summary": "ok"},
            }
        )

    monkeypatch.setattr("interview_analytics_agent.quick_record.requests.post", _fake_post)
    monkeypatch.setattr("interview_analytics_agent.quick_record.requests.get", _fake_get)

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

    assert calls["post"][0][0] == "http://127.0.0.1:8010/v1/meetings/start"
    assert calls["post"][1][0] == "http://127.0.0.1:8010/v1/meetings/quick-123/chunks"
    assert calls["get"][0][0] == "http://127.0.0.1:8010/v1/meetings/quick-123"


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
