from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin


class TimetableStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    INFEASIBLE = "INFEASIBLE"
    PRECHECK_FAILED = "PRECHECK_FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class Timetable(IdMixin, TimestampMixin, Base):
    __tablename__ = "timetables"

    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[TimetableStatus] = mapped_column(Enum(TimetableStatus, native_enum=False, length=16),
                                                    default=TimetableStatus.DRAFT, index=True)
    academic_year: Mapped[str | None] = mapped_column(String(16))
    term: Mapped[str | None] = mapped_column(String(8))  # ODD (Sem I, III, …) | EVEN (Sem II, IV, …)
    # Scope: empty list = all programmes
    programme_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    semesters: Mapped[list[int]] = mapped_column(JSON, default=list)
    quality_score: Mapped[float | None] = mapped_column()
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("timetables.id", ondelete="SET NULL"))
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(String(1000))
    published_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))  # sealed on publish
    notice: Mapped[str | None] = mapped_column(String(300))  # e.g. "Unpublished: replaced by …"
    last_run_id: Mapped[str | None] = mapped_column(String(36))

    entries: Mapped[list["TimetableEntry"]] = relationship(
        back_populates="timetable", cascade="all, delete-orphan", lazy="selectin"
    )


class TimetableEntry(IdMixin, Base):
    __tablename__ = "timetable_entries"
    __table_args__ = (UniqueConstraint("timetable_id", "session_key"),)

    timetable_id: Mapped[str] = mapped_column(ForeignKey("timetables.id", ondelete="CASCADE"), index=True)
    session_key: Mapped[str] = mapped_column(String(160))
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    group_id: Mapped[str] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"))
    faculty_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    day: Mapped[int | None] = mapped_column(Integer)          # None = unassigned
    start_period: Mapped[int | None] = mapped_column(Integer)
    length: Mapped[int] = mapped_column(Integer, default=1)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    timetable: Mapped[Timetable] = relationship(back_populates="entries")


class GenerationRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "generation_runs"

    timetable_id: Mapped[str] = mapped_column(ForeignKey("timetables.id", ondelete="CASCADE"), index=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, native_enum=False, length=20), default=RunStatus.QUEUED)
    mode: Mapped[str] = mapped_column(String(16), default="full")  # full | unlocked
    time_limit_s: Mapped[int] = mapped_column(Integer)
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    diagnostics: Mapped[list[dict]] = mapped_column(JSON, default=list)
    unassigned: Mapped[list[dict]] = mapped_column(JSON, default=list)
