"""University calendar -> discrete periods.

Periods are generated per working day by stepping ``period_minutes`` from ``day_start``. A period
may never overlap a break: generation jumps to the end of the break instead. Two periods are
*contiguous* only if one ends exactly when the next begins, so a practical can never span a break.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

Slot = tuple[int, int]  # (day, period index)


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Period:
    day: int
    index: int
    start: int
    end: int

    @property
    def label(self) -> str:
        return f"{fmt(self.start)}–{fmt(self.end)}"


@dataclass(frozen=True)
class BreakSpec:
    name: str
    start: int
    end: int
    days: frozenset[int] | None = None  # None = all days

    def applies(self, day: int) -> bool:
        return self.days is None or day in self.days


@dataclass(frozen=True)
class TimeRange:
    day: int
    start: int
    end: int

    @classmethod
    def parse(cls, d: dict) -> "TimeRange":
        return cls(int(d["day"]), to_minutes(d["start"]), to_minutes(d["end"]))


@dataclass
class TimeGrid:
    working_days: list[int]
    day_start: int
    day_end: int
    period_minutes: int
    breaks: list[BreakSpec] = field(default_factory=list)
    periods: dict[int, list[Period]] = field(init=False)

    def __post_init__(self) -> None:
        if self.period_minutes <= 0:
            raise ValueError("Period duration must be positive")
        self.periods = {d: self._build_day(d) for d in sorted(set(self.working_days))}

    def _build_day(self, day: int) -> list[Period]:
        out: list[Period] = []
        t = self.day_start
        day_breaks = sorted((b for b in self.breaks if b.applies(day)), key=lambda b: b.start)
        while t + self.period_minutes <= self.day_end:
            end = t + self.period_minutes
            clash = [b for b in day_breaks if b.start < end and t < b.end]
            if clash:
                t = max(b.end for b in clash)
                continue
            out.append(Period(day, len(out), t, end))
            t = end
        return out

    # ------------------------------------------------------------------ queries
    @property
    def days(self) -> list[int]:
        return list(self.periods)

    def all_slots(self) -> list[Slot]:
        return [(d, p.index) for d, ps in self.periods.items() for p in ps]

    def n_periods(self, day: int) -> int:
        return len(self.periods.get(day, []))

    def period(self, day: int, index: int) -> Period | None:
        ps = self.periods.get(day)
        if ps is None or not 0 <= index < len(ps):
            return None
        return ps[index]

    def contiguous(self, day: int, start: int, length: int) -> bool:
        ps = self.periods.get(day)
        if ps is None or start < 0 or start + length > len(ps):
            return False
        return all(ps[i].end == ps[i + 1].start for i in range(start, start + length - 1))

    def covered(self, day: int, start: int, length: int) -> list[Slot]:
        return [(day, start + i) for i in range(length)]

    def longest_block(self) -> int:
        best = 0
        for ps in self.periods.values():
            run = 0
            for i, p in enumerate(ps):
                run = run + 1 if i and ps[i - 1].end == p.start else 1
                best = max(best, run)
        return best

    def slots_within(self, ranges: Iterable[TimeRange]) -> set[Slot]:
        """Periods lying fully inside at least one range."""
        out: set[Slot] = set()
        for r in ranges:
            for p in self.periods.get(r.day, []):
                if r.start <= p.start and p.end <= r.end:
                    out.add((p.day, p.index))
        return out

    def slots_touching(self, ranges: Iterable[TimeRange]) -> set[Slot]:
        """Periods overlapping at least one range."""
        out: set[Slot] = set()
        for r in ranges:
            for p in self.periods.get(r.day, []):
                if p.start < r.end and r.start < p.end:
                    out.add((p.day, p.index))
        return out

    def slot_label(self, slot: Slot) -> str:
        p = self.period(*slot)
        return f"{DAY_SHORT[slot[0]]} {p.label}" if p else f"{DAY_SHORT[slot[0]]} P{slot[1] + 1}"

    def to_dict(self) -> dict:
        return {
            "days": [{"day": d, "name": DAY_NAMES[d], "short": DAY_SHORT[d],
                      "periods": [{"index": p.index, "start": fmt(p.start), "end": fmt(p.end)} for p in ps]}
                     for d, ps in self.periods.items()],
            "breaks": [{"name": b.name, "start": fmt(b.start), "end": fmt(b.end),
                        "days": sorted(b.days) if b.days is not None else None} for b in self.breaks],
            "periods_per_week": sum(len(ps) for ps in self.periods.values()),
            "longest_block": self.longest_block(),
        }
