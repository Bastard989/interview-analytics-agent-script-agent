"""
ORM-модели базы данных.

Назначение:
- Хранение состояния встреч
- Хранение текстовых артефактов
- Трассируемость пайплайна
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from interview_analytics_agent.domain.enums import ConsentStatus, PipelineStatus


# =============================================================================
# BASE
# =============================================================================
class Base(DeclarativeBase):
    pass


# =============================================================================
# MEETING
# =============================================================================
class Meeting(Base):
    """
    Основная сущность — встреча.
    """

    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[PipelineStatus] = mapped_column(Enum(PipelineStatus), nullable=False)
    consent: Mapped[ConsentStatus] = mapped_column(Enum(ConsentStatus), nullable=False)

    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    raw_transcript: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enhanced_transcript: Mapped[str] = mapped_column(Text, default="", nullable=False)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )


# =============================================================================
# TRANSCRIPT SEGMENTS
# =============================================================================
class TranscriptSegment(Base):
    """
    Сегмент текста (сырой / улучшенный).
    """

    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), nullable=False)

    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(64), nullable=True)

    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enhanced_text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    meeting: Mapped[Meeting] = relationship(back_populates="segments")
