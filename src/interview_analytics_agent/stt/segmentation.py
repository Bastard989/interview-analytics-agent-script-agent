"""
Сегментация аудио.

Назначение:
- определение границ фраз
- работа с паузами
"""


def is_silence(frame_energy: float, threshold: float = 0.01) -> bool:
    return frame_energy < threshold
