"""
Локальный STT на базе faster-whisper.

Что делает:
- принимает bytes аудио чанка
- декодирует через ffmpeg (нужен пакет ffmpeg в образе)
- запускает Whisper модель локально
- возвращает текст + (примерную) уверенность

Примечание:
- для реально качественного realtime лучше подавать PCM16/mono/16k,
  но в MVP достаточно принять байты, декодировать, распознать.
"""

from __future__ import annotations

import io

import av  # PyAV (ffmpeg bindings)
import numpy as np
from faster_whisper import WhisperModel

from interview_analytics_agent.common.config import get_settings

from .base import STTProvider, STTResult


def _decode_audio_to_float32(audio_bytes: bytes, target_sr: int = 16000) -> np.ndarray:
    """
    Декодирует произвольный аудио-контейнер/кодек в моно float32 16kHz.

    Требование:
    - ffmpeg/libav должен быть доступен (через PyAV)
    """
    container = av.open(io.BytesIO(audio_bytes))
    stream = next(s for s in container.streams if s.type == "audio")
    resampler = av.audio.resampler.AudioResampler(format="fltp", layout="mono", rate=target_sr)

    samples: list[np.ndarray] = []
    for frame in container.decode(stream):
        frame = resampler.resample(frame)
        # frame.to_ndarray() -> shape (channels, samples) в float
        arr = frame.to_ndarray()
        if arr.ndim == 2:
            arr = arr[0]
        samples.append(arr.astype(np.float32))

    if not samples:
        return np.zeros((0,), dtype=np.float32)

    return np.concatenate(samples)


class WhisperLocalProvider(STTProvider):
    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
        vad_filter: bool | None = None,
        beam_size: int | None = None,
        **_: object,
    ) -> None:
        s = get_settings()

        # берём параметры из аргументов, иначе из настроек
        model_size = model_size or s.whisper_model_size
        device = device or s.whisper_device
        compute_type = compute_type or s.whisper_compute_type

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )

        self.language = language or s.whisper_language
        self.vad_filter = s.whisper_vad_filter if vad_filter is None else vad_filter
        self.beam_size = beam_size or s.whisper_beam_size

    def transcribe_chunk(self, *, audio: bytes, sample_rate: int) -> STTResult:
        wav = _decode_audio_to_float32(audio, target_sr=16000)
        if wav.size == 0:
            return STTResult(text="", confidence=None)

        segments, info = self.model.transcribe(
            wav,
            language=self.language,
            vad_filter=self.vad_filter,
            beam_size=self.beam_size,
        )

        text_parts: list[str] = []
        for seg in segments:
            if seg.text:
                text_parts.append(seg.text.strip())

        text = " ".join([t for t in text_parts if t]).strip()

        # faster-whisper не даёт "confidence" как одно число стабильно,
        # оставим None, позже можно считать среднюю logprob.
        return STTResult(text=text, confidence=None, speaker=None)
