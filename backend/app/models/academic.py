"""Coordinator inputs: calendar, rooms, programmes, groups, batches, faculty, subjects, constraints."""
from __future__ import annotations

from enum import StrEnum

from sqlalchemy import JSON, Boolean, Column, Enum, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin


class RoomKind(StrEnum):
    CLASSROOM = "CLASSROOM"
    LAB = "LAB"


class SubjectKind(StrEnum):
    THEORY = "THEORY"
    PRACTICAL = "PRACTICAL"


class Level(StrEnum):
    UG = "UG"
    PG = "PG"
    INTEGRATED = "INTEGRATED"
    PHD = "PHD"
    DIPLOMA = "DIPLOMA"


class ConstraintMode(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    OFF = "OFF"


def _enum(e):
    return Enum(e, native_enum=False, length=16)


class CalendarSettings(Base):
    __tablename__ = "calendar_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    working_days: Mapped[list[int]] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])  # 0 = Monday
    day_start: Mapped[str] = mapped_column(String(5), default="09:00")
    day_end: Mapped[str] = mapped_column(String(5), default="17:00")
    period_minutes: Mapped[int] = mapped_column(Integer, default=60)


class Break(IdMixin, Base):
    __tablename__ = "breaks"

    name: Mapped[str] = mapped_column(String(48))
    start_time: Mapped[str] = mapped_column(String(5))
    end_time: Mapped[str] = mapped_column(String(5))
    days: Mapped[list[int] | None] = mapped_column(JSON)  # None = every working day


class LabType(IdMixin, TimestampMixin, Base):
    __tablename__ = "lab_types"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(String(256))


class Room(IdMixin, TimestampMixin, Base):
    __tablename__ = "rooms"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(96))
    kind: Mapped[RoomKind] = mapped_column(_enum(RoomKind))
    lab_type_id: Mapped[str | None] = mapped_column(ForeignKey("lab_types.id", ondelete="RESTRICT"))
    capacity: Mapped[int] = mapped_column(Integer)
    building: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    unavailable: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{day,start,end}]

    lab_type: Mapped[LabType | None] = relationship(lazy="joined")


class Programme(IdMixin, TimestampMixin, Base):
    __tablename__ = "programmes"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    level: Mapped[Level] = mapped_column(_enum(Level))
    school: Mapped[str] = mapped_column(String(160))
    duration_semesters: Mapped[int] = mapped_column(Integer)

    # Programme coordinator (a COORDINATOR/ADMIN user). Plain column: a DB-level FK would create a
    # users -> student_groups -> programmes -> users cycle; integrity is enforced in the service layer.
    coordinator_id: Mapped[str | None] = mapped_column(String(36), index=True)

    groups: Mapped[list["StudentGroup"]] = relationship(back_populates="programme", cascade="all, delete-orphan")
    coordinator = relationship("User", primaryjoin="foreign(Programme.coordinator_id) == User.id", viewonly=True,
                               lazy="joined")


class StudentGroup(IdMixin, TimestampMixin, Base):
    """A class section: programme + semester + section."""

    __tablename__ = "student_groups"
    __table_args__ = (UniqueConstraint("programme_id", "semester", "section"),)

    programme_id: Mapped[str] = mapped_column(ForeignKey("programmes.id", ondelete="CASCADE"), index=True)
    semester: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(8), default="A")
    strength: Mapped[int] = mapped_column(Integer)
    max_periods_per_day: Mapped[int | None] = mapped_column(Integer)
    home_room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))  # the class "Venue"

    programme: Mapped[Programme] = relationship(back_populates="groups", lazy="joined")
    batches: Mapped[list["Batch"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="Batch.name", lazy="selectin"
    )

    @property
    def label(self) -> str:
        return f"{self.programme.code} Sem {self.semester}-{self.section}"


class Batch(IdMixin, TimestampMixin, Base):
    __tablename__ = "batches"
    __table_args__ = (UniqueConstraint("group_id", "name"),)

    group_id: Mapped[str] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(16))
    strength: Mapped[int] = mapped_column(Integer)

    group: Mapped[StudentGroup] = relationship(back_populates="batches")


faculty_programmes = Table(
    "faculty_programmes",
    Base.metadata,
    Column("faculty_id", ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True),
    Column("programme_id", ForeignKey("programmes.id", ondelete="CASCADE"), primary_key=True),
)

subject_faculty = Table(
    "subject_faculty",
    Base.metadata,
    Column("subject_id", ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
    Column("faculty_id", ForeignKey("faculty.id", ondelete="CASCADE"), primary_key=True),
)


class Faculty(IdMixin, TimestampMixin, Base):
    __tablename__ = "faculty"

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    designation: Mapped[str] = mapped_column(String(64))
    school: Mapped[str] = mapped_column(String(160))
    max_periods_per_day: Mapped[int | None] = mapped_column(Integer)
    max_periods_per_week: Mapped[int | None] = mapped_column(Integer)
    # Availability as time ranges (robust to period-length changes):
    # {"available": [{day,start,end}] | null (= whole working week),
    #  "unavailable": [{day,start,end}], "preferred": [{day,start,end}], "commitments": [{day,start,end,reason}]}
    availability: Mapped[dict] = mapped_column(JSON, default=dict)

    subjects: Mapped[list["Subject"]] = relationship(secondary=subject_faculty, back_populates="faculty")
    # Programmes this faculty member may be assigned to teach in (empty = any programme).
    programmes: Mapped[list[Programme]] = relationship(secondary=faculty_programmes, lazy="selectin")

    @property
    def programme_ids(self) -> list[str]:
        return [p.id for p in self.programmes]


class Subject(IdMixin, TimestampMixin, Base):
    __tablename__ = "subjects"

    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    short_name: Mapped[str] = mapped_column(String(16), default="")  # e.g. "VAPT" — shown on timetables
    programme_id: Mapped[str] = mapped_column(ForeignKey("programmes.id", ondelete="CASCADE"), index=True)
    semester: Mapped[int] = mapped_column(Integer)
    kind: Mapped[SubjectKind] = mapped_column(_enum(SubjectKind))
    periods_per_week: Mapped[int] = mapped_column(Integer, default=0)      # THEORY
    sessions_per_week: Mapped[int] = mapped_column(Integer, default=0)     # PRACTICAL
    consecutive_periods: Mapped[int] = mapped_column(Integer, default=1)   # PRACTICAL
    lab_type_id: Mapped[str | None] = mapped_column(ForeignKey("lab_types.id", ondelete="RESTRICT"))
    credits: Mapped[int | None] = mapped_column(Integer)

    programme: Mapped[Programme] = relationship(lazy="joined")
    lab_type: Mapped[LabType | None] = relationship(lazy="joined")
    faculty: Mapped[list[Faculty]] = relationship(
        secondary=subject_faculty, back_populates="subjects", lazy="selectin"
    )


class FixedSession(IdMixin, TimestampMixin, Base):
    """A session pinned to a slot by the coordinator (mandatory)."""

    __tablename__ = "fixed_sessions"

    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    group_id: Mapped[str] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)
    start_period: Mapped[int] = mapped_column(Integer)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(160))


class RuleKind(StrEnum):
    CLASS_BLOCK = "CLASS_BLOCK"                      # a class is never scheduled in these periods
    SUBJECT_WINDOW = "SUBJECT_WINDOW"                # a subject only in these days/hours
    FACULTY_MAX_CONSECUTIVE = "FACULTY_MAX_CONSECUTIVE"  # no more than N periods in a row
    ROOM_RESERVED = "ROOM_RESERVED"                  # a room only for some programmes


class CustomRule(IdMixin, TimestampMixin, Base):
    """Structured rules added by coordinators (safe: typed parameters, no free-form code)."""

    __tablename__ = "custom_rules"

    kind: Mapped[RuleKind] = mapped_column(Enum(RuleKind, native_enum=False, length=32))
    mode: Mapped[ConstraintMode] = mapped_column(_enum(ConstraintMode))
    weight: Mapped[int] = mapped_column(Integer, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(String(160))


class ConstraintSetting(Base):
    __tablename__ = "constraint_settings"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    mode: Mapped[ConstraintMode] = mapped_column(_enum(ConstraintMode))
    weight: Mapped[int] = mapped_column(Integer, default=5)
    value: Mapped[int | None] = mapped_column(Integer)
