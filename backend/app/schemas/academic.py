from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from app.models.academic import ConstraintMode, Level, RoomKind, RuleKind, SubjectKind
from app.schemas.common import HHMM, Code, CommitmentIn, Day, Name, ReadModel, ShortText, StrictModel, TimeRangeIn

Strength = Annotated[int, Field(ge=1, le=500)]       # students in a class/batch
Capacity = Annotated[int, Field(ge=1, le=1000)]      # seats in a room
Semester = Annotated[int, Field(ge=1, le=12)]


# ---------------------------------------------------------------- calendar
class BreakIn(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=48)]
    start_time: HHMM
    end_time: HHMM
    days: list[Day] | None = None


class CalendarIn(StrictModel):
    working_days: Annotated[list[Day], Field(min_length=1, max_length=7)]
    day_start: HHMM
    day_end: HHMM
    period_minutes: Annotated[int, Field(ge=15, le=240)]
    breaks: list[BreakIn] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _check(self):
        if self.day_start >= self.day_end:
            raise ValueError("Day start must be before day end")
        for b in self.breaks:
            if b.start_time >= b.end_time:
                raise ValueError(f"Break '{b.name}' must start before it ends")
        self.working_days = sorted(set(self.working_days))
        return self


# ---------------------------------------------------------------- lab types / rooms
class LabTypeIn(StrictModel):
    name: Name
    description: ShortText | None = None


class LabTypeOut(ReadModel):
    id: str
    name: str
    description: str | None


class RoomIn(StrictModel):
    code: Code
    name: Name
    kind: RoomKind
    lab_type_id: str | None = None
    capacity: Capacity
    building: Annotated[str, Field(max_length=64)] | None = None
    is_active: bool = True
    unavailable: list[TimeRangeIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _lab(self):
        if self.kind == RoomKind.CLASSROOM:
            self.lab_type_id = None
        return self


class RoomUpdate(StrictModel):
    code: Code | None = None
    name: Name | None = None
    kind: RoomKind | None = None
    lab_type_id: str | None = None
    capacity: Capacity | None = None
    building: Annotated[str, Field(max_length=64)] | None = None
    is_active: bool | None = None
    unavailable: list[TimeRangeIn] | None = Field(default=None, max_length=100)


class RoomOut(ReadModel):
    id: str
    code: str
    name: str
    kind: RoomKind
    lab_type_id: str | None
    lab_type: LabTypeOut | None
    capacity: int
    building: str | None
    is_active: bool
    unavailable: list[dict]


# ---------------------------------------------------------------- programmes / groups / batches
class ProgrammeIn(StrictModel):
    code: Code
    name: Name
    level: Level
    school: Name
    duration_semesters: Semester
    coordinator_id: str | None = None


class ProgrammeUpdate(StrictModel):
    code: Code | None = None
    name: Name | None = None
    level: Level | None = None
    school: Name | None = None
    duration_semesters: Semester | None = None
    coordinator_id: str | None = None


class BatchIn(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=16)]
    strength: Strength


class BatchOut(ReadModel):
    id: str
    name: str
    strength: int


class GroupIn(StrictModel):
    programme_id: str
    semester: Semester
    section: Annotated[str, Field(min_length=1, max_length=8)] = "A"
    strength: Strength
    max_periods_per_day: Annotated[int, Field(ge=1, le=16)] | None = None
    home_room_id: str | None = None
    batches: list[BatchIn] = Field(default_factory=list, max_length=12)


class GroupUpdate(StrictModel):
    semester: Semester | None = None
    section: Annotated[str, Field(min_length=1, max_length=8)] | None = None
    strength: Strength | None = None
    max_periods_per_day: Annotated[int, Field(ge=1, le=16)] | None = None
    home_room_id: str | None = None
    batches: list[BatchIn] | None = Field(default=None, max_length=12)


class GroupOut(ReadModel):
    id: str
    programme_id: str
    semester: int
    section: str
    strength: int
    max_periods_per_day: int | None
    home_room_id: str | None
    batches: list[BatchOut]
    label: str


class PersonBrief(ReadModel):
    id: str
    full_name: str
    email: str


class ProgrammeOut(ReadModel):
    id: str
    code: str
    name: str
    level: Level
    school: str
    duration_semesters: int
    coordinator_id: str | None
    coordinator: PersonBrief | None = None
    created_at: datetime


# ---------------------------------------------------------------- faculty
class AvailabilityIn(StrictModel):
    available: list[TimeRangeIn] | None = Field(default=None, max_length=200)  # None = whole working week
    unavailable: list[TimeRangeIn] = Field(default_factory=list, max_length=200)
    preferred: list[TimeRangeIn] = Field(default_factory=list, max_length=200)
    commitments: list[CommitmentIn] = Field(default_factory=list, max_length=100)


class FacultyIn(StrictModel):
    code: Code
    name: Name
    email: Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    designation: Name
    school: Name
    max_periods_per_day: Annotated[int, Field(ge=1, le=16)] | None = None
    max_periods_per_week: Annotated[int, Field(ge=1, le=80)] | None = None
    availability: AvailabilityIn = Field(default_factory=AvailabilityIn)
    programme_ids: list[str] = Field(default_factory=list, max_length=50)


class FacultyUpdate(StrictModel):
    code: Code | None = None
    name: Name | None = None
    email: Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")] | None = None
    designation: Name | None = None
    school: Name | None = None
    max_periods_per_day: Annotated[int, Field(ge=1, le=16)] | None = None
    max_periods_per_week: Annotated[int, Field(ge=1, le=80)] | None = None
    availability: AvailabilityIn | None = None
    programme_ids: list[str] | None = Field(default=None, max_length=50)


class FacultyOut(ReadModel):
    id: str
    code: str
    name: str
    email: str
    designation: str
    school: str
    max_periods_per_day: int | None
    max_periods_per_week: int | None
    availability: dict
    programme_ids: list[str]


# ---------------------------------------------------------------- subjects
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16,
                                             pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._\-/()&+]*$")]


class SubjectIn(StrictModel):
    code: Code
    name: Name
    short_name: ShortName
    programme_id: str
    semester: Semester
    kind: SubjectKind
    periods_per_week: Annotated[int, Field(ge=0, le=20)] = 0
    sessions_per_week: Annotated[int, Field(ge=0, le=10)] = 0
    consecutive_periods: Annotated[int, Field(ge=1, le=6)] = 1
    lab_type_id: str | None = None
    credits: Annotated[int, Field(ge=0, le=20)] | None = None
    faculty_ids: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _kind(self):
        if self.kind == SubjectKind.THEORY:
            if self.periods_per_week < 1:
                raise ValueError("A theory subject needs at least 1 period per week")
            self.sessions_per_week, self.consecutive_periods, self.lab_type_id = 0, 1, None
        else:
            if self.sessions_per_week < 1:
                raise ValueError("A practical needs at least 1 session per week")
            self.periods_per_week = 0
        return self


class SubjectUpdate(StrictModel):
    code: Code | None = None
    name: Name | None = None
    short_name: ShortName | None = None
    programme_id: str | None = None
    semester: Semester | None = None
    kind: SubjectKind | None = None
    periods_per_week: Annotated[int, Field(ge=0, le=20)] | None = None
    sessions_per_week: Annotated[int, Field(ge=0, le=10)] | None = None
    consecutive_periods: Annotated[int, Field(ge=1, le=6)] | None = None
    lab_type_id: str | None = None
    credits: Annotated[int, Field(ge=0, le=20)] | None = None
    faculty_ids: list[str] | None = Field(default=None, max_length=4)


class FacultyBrief(ReadModel):
    id: str
    code: str
    name: str


class SubjectOut(ReadModel):
    id: str
    code: str
    name: str
    short_name: str
    programme_id: str
    semester: int
    kind: SubjectKind
    periods_per_week: int
    sessions_per_week: int
    consecutive_periods: int
    lab_type_id: str | None
    lab_type: LabTypeOut | None
    credits: int | None
    faculty: list[FacultyBrief]


# ---------------------------------------------------------------- fixed sessions / constraints
class FixedSessionIn(StrictModel):
    subject_id: str
    group_id: str
    batch_id: str | None = None
    day: Day
    start_period: Annotated[int, Field(ge=0, le=30)]
    room_id: str | None = None
    note: ShortText | None = None


class FixedSessionOut(ReadModel):
    id: str
    subject_id: str
    group_id: str
    batch_id: str | None
    day: int
    start_period: int
    room_id: str | None
    note: str | None


class ConstraintIn(StrictModel):
    key: Annotated[str, Field(max_length=48)]
    mode: ConstraintMode
    weight: Annotated[int, Field(ge=0, le=10)] = 5
    value: Annotated[int, Field(ge=0, le=100)] | None = None


class ConstraintOut(ReadModel):
    key: str
    mode: ConstraintMode
    weight: int
    value: int | None


class CustomRuleIn(StrictModel):
    kind: RuleKind
    mode: ConstraintMode = ConstraintMode.HARD
    weight: Annotated[int, Field(ge=0, le=10)] = 5
    enabled: bool = True
    params: dict = Field(default_factory=dict)
    note: ShortText | None = None


class CustomRuleUpdate(StrictModel):
    mode: ConstraintMode | None = None
    weight: Annotated[int, Field(ge=0, le=10)] | None = None
    enabled: bool | None = None
    params: dict | None = None
    note: ShortText | None = None


class CustomRuleOut(ReadModel):
    id: str
    kind: RuleKind
    mode: ConstraintMode
    weight: int
    enabled: bool
    params: dict
    note: str | None
