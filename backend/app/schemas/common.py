from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

T = TypeVar("T")

HHMM = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Day = Annotated[int, Field(ge=0, le=6)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32,
                                        pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._\-/()&]*$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class StrictModel(BaseModel):
    """Input model: unknown fields are rejected (blocks mass-assignment), strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimeRangeIn(StrictModel):
    day: Day
    start: HHMM
    end: HHMM

    @model_validator(mode="after")
    def _order(self):
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class CommitmentIn(TimeRangeIn):
    reason: ShortText = ""


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
