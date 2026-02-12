"""
Lightweight diarization (speaker assignment) with graceful degradation.
"""

from __future__ import annotations

import io
import math
import threading
from dataclasses import dataclass

_STATE_LOCK = threading.Lock()


@dataclass
class _SpeakerProto:
    label: str
    centroid: list[float]
    count: int


_STATE: dict[str, list[_SpeakerProto]] = {}


def _norm(label: str) -> str:
    return (label or "").strip().lower()


def _dot(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=False)))


def _norm_l2(v: list[float]) -> float:
    return math.sqrt(float(sum(x * x for x in v)))


def _cosine(a: list[float], b: list[float]) -> float:
    denom = _norm_l2(a) * _norm_l2(b)
    if denom <= 1e-9:
        return 0.0
    return _dot(a, b) / denom


def _normalize(v: list[float]) -> list[float] | None:
    norm = _norm_l2(v)
    if norm <= 1e-9:
        return None
    return [x / norm for x in v]


def _decode_audio_embedding(audio_bytes: bytes | None) -> list[float] | None:
    if not audio_bytes:
        return None
    try:
        import av
    except Exception:
        return None

    try:
        container = av.open(io.BytesIO(audio_bytes))
        stream = next(s for s in container.streams if s.type == "audio")
    except Exception:
        return None

    signal: list[float] = []
    try:
        for frame in container.decode(stream):
            arr = frame.to_ndarray()
            data = arr.tolist() if hasattr(arr, "tolist") else []
            if not data:
                continue
            if isinstance(data[0], list):
                channels = [list(map(float, ch)) for ch in data if isinstance(ch, list)]
                if not channels:
                    continue
                min_len = min(len(ch) for ch in channels)
                for idx in range(min_len):
                    signal.append(sum(ch[idx] for ch in channels) / len(channels))
            else:
                signal.extend(float(x) for x in data)
    except Exception:
        return None

    if len(signal) < 256:
        return None
    sample = signal[: min(len(signal), 16000)]

    # lightweight frequency embedding via DFT over low-frequency bins
    bins = 24
    emb: list[float] = []
    n = len(sample)
    for k in range(1, bins + 1):
        real = 0.0
        imag = 0.0
        for t, x in enumerate(sample):
            angle = 2.0 * math.pi * k * t / n
            real += x * math.cos(angle)
            imag -= x * math.sin(angle)
        emb.append(math.sqrt(real * real + imag * imag) / n)
    return _normalize(emb)


def _assign_by_embedding(meeting_id: str, embedding: list[float]) -> str:
    with _STATE_LOCK:
        protos = _STATE.setdefault(meeting_id, [])
        if not protos:
            proto = _SpeakerProto(label="Speaker-A", centroid=embedding, count=1)
            protos.append(proto)
            return proto.label

        best_idx = -1
        best_sim = -1.0
        for idx, proto in enumerate(protos):
            sim = _cosine(embedding, proto.centroid)
            if sim > best_sim:
                best_idx = idx
                best_sim = sim

        if best_idx >= 0 and best_sim >= 0.86:
            proto = protos[best_idx]
            n = proto.count + 1
            proto.centroid = [
                (proto.centroid[i] * proto.count + embedding[i]) / n
                for i in range(min(len(proto.centroid), len(embedding)))
            ]
            proto.count = n
            return proto.label

        if len(protos) < 4:
            label = f"Speaker-{chr(ord('A') + len(protos))}"
            protos.append(_SpeakerProto(label=label, centroid=embedding, count=1))
            return label

        return protos[best_idx].label if best_idx >= 0 else "Speaker-A"


def resolve_speaker(
    *,
    hint: str | None,
    raw_text: str | None = None,
    seq: int | None = None,
    meeting_id: str | None = None,
    audio_bytes: bytes | None = None,
) -> str | None:
    normalized = _norm(hint or "")
    if normalized:
        return str(hint).strip()

    if meeting_id:
        embedding = _decode_audio_embedding(audio_bytes)
        if embedding is not None:
            return _assign_by_embedding(str(meeting_id), embedding)

    text = _norm(raw_text or "")
    if text.startswith(("интервьюер:", "interviewer:")):
        return "Interviewer"
    if text.startswith(("кандидат:", "candidate:")):
        return "Candidate"
    if text.endswith("?") or "почему" in text or "why" in text:
        return "Interviewer"

    seq_num = int(seq or 0)
    if seq_num > 0:
        return "Speaker-A" if seq_num % 2 == 1 else "Speaker-B"
    return None
