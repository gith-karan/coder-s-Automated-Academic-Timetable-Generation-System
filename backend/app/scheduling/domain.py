"""Pure scheduling domain. No database, no HTTP — easy to test and reuse.

The engine schedules *session units*: one theory period, or one practical session of L
consecutive periods for one batch. Students are modelled as *audience atoms* (the batches of a
class, or the class itself if it has no batches). A whole-class unit uses every atom of the
class; a batch unit uses only its own atom. "At most one unit per atom per period" therefore
gives both PS rules at once: lectures never overlap any batch practical, while different batches
may run practicals in parallel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from app.scheduling.timegrid import Slot, TimeGrid

THEORY = "THEORY"
PRACTICAL = "PRACTICAL"
CLASSROOM = "CLASSROOM"
LAB = "LAB"


@dataclass(frozen=True)
class RoomInfo:
    id: str
    code: str
    name: str
    kind: str
    lab_type: str | None
    capacity: int
    blocked: frozenset[Slot] = frozenset()


@dataclass(frozen=True)
class FacultyInfo:
    id: str
    code: str
    name: str
    available: frozenset[Slot]
    preferred: frozenset[Slot] = frozenset()
    max_per_day: int | None = None
    max_per_week: int | None = None


@dataclass(frozen=True)
class GroupInfo:
    id: str
    label: str
    strength: int
    atoms: tuple[str, ...]
    batch_labels: dict[str, str] = field(default_factory=dict, hash=False, compare=False)
    max_per_day: int | None = None
    home_room: str | None = None  # preferred room for the class's lectures (its "Venue")


@dataclass(frozen=True)
class SessionUnit:
    key: str
    subject_id: str
    subject_code: str
    subject_name: str
    kind: str
    group_id: str
    batch_id: str | None
    audience: str          # "M.Sc. DFIS Sem 1-A" or "M.Sc. DFIS Sem 1-A / B1"
    strength: int
    length: int
    faculty_ids: tuple[str, ...]
    atoms: tuple[str, ...]
    room_kind: str
    lab_type: str | None
    index: int             # n-th unit of this (subject, audience)

    @property
    def family(self) -> tuple[str, str, str | None]:
        """Units in the same family are interchangeable (used for symmetry breaking & spreading)."""
        return (self.subject_id, self.group_id, self.batch_id)

    @property
    def label(self) -> str:
        return f"{self.subject_code} ({self.audience})"


@dataclass(frozen=True)
class Placement:
    key: str
    day: int
    period: int
    room_id: str


@dataclass(frozen=True)
class Pin:
    key: str
    day: int
    period: int
    room_id: str | None = None
    reason: str = "fixed"  # fixed | locked


@dataclass
class Options:
    spread_mode: str = "SOFT"          # HARD | SOFT | OFF — max 1 theory period of a subject per day
    spread_weight: int = 5
    preferred_weight: int = 3
    stability_weight: int = 4
    late_weight: int = 1               # gentle push away from the last period of the day
    home_room_weight: int = 2          # lectures preferably in the class's home room
    allow_theory_in_lab: bool = False
    faculty_daily_default: int | None = None
    group_daily_default: int | None = None


@dataclass
class Problem:
    grid: TimeGrid
    rooms: dict[str, RoomInfo]
    faculty: dict[str, FacultyInfo]
    groups: dict[str, GroupInfo]
    units: list[SessionUnit]
    pins: dict[str, Pin] = field(default_factory=dict)
    previous: dict[str, Placement] = field(default_factory=dict)
    options: Options = field(default_factory=Options)
    warnings: list[dict] = field(default_factory=list)

    @cached_property
    def unit_by_key(self) -> dict[str, SessionUnit]:
        return {u.key: u for u in self.units}

    # ----------------------------------------------------------- candidates
    def faculty_daily_limit(self, fid: str) -> int | None:
        f = self.faculty.get(fid)
        return (f.max_per_day if f and f.max_per_day else None) or self.options.faculty_daily_default

    def group_daily_limit(self, gid: str) -> int | None:
        g = self.groups.get(gid)
        return (g.max_per_day if g and g.max_per_day else None) or self.options.group_daily_default

    def room_suitable(self, unit: SessionUnit, room: RoomInfo) -> bool:
        if room.capacity < unit.strength:
            return False
        if unit.room_kind == LAB:
            return room.kind == LAB and (unit.lab_type is None or room.lab_type == unit.lab_type)
        return room.kind == CLASSROOM or (self.options.allow_theory_in_lab and room.kind == LAB)

    @cached_property
    def _rooms_for(self) -> dict[str, list[RoomInfo]]:
        return {u.key: sorted((r for r in self.rooms.values() if self.room_suitable(u, r)),
                              key=lambda r: (r.capacity, r.code)) for u in self.units}

    def rooms_for(self, unit: SessionUnit) -> list[RoomInfo]:
        return self._rooms_for[unit.key]

    def time_ok_for_faculty(self, unit: SessionUnit, day: int, start: int) -> bool:
        if not self.grid.contiguous(day, start, unit.length):
            return False
        cov = self.grid.covered(day, start, unit.length)
        return all(all(s in self.faculty[f].available for s in cov) for f in unit.faculty_ids if f in self.faculty)

    @cached_property
    def _starts_for(self) -> dict[str, list[Slot]]:
        out: dict[str, list[Slot]] = {}
        for u in self.units:
            out[u.key] = [(d, p) for d in self.grid.days for p in range(self.grid.n_periods(d))
                          if self.time_ok_for_faculty(u, d, p)]
        return out

    def starts_for(self, unit: SessionUnit) -> list[Slot]:
        return self._starts_for[unit.key]

    def room_free(self, room: RoomInfo, day: int, start: int, length: int) -> bool:
        return not any(s in room.blocked for s in self.grid.covered(day, start, length))


# ---------------------------------------------------------------- occupancy
def resource_keys(unit: SessionUnit, room_id: str | None) -> list[tuple[str, str]]:
    keys = [("faculty", f) for f in unit.faculty_ids]
    keys += [("atom", a) for a in unit.atoms]
    if room_id:
        keys.append(("room", room_id))
    return keys


def build_occupancy(problem: Problem, placements: dict[str, Placement],
                    exclude: str | None = None) -> dict[tuple[str, str, int, int], list[str]]:
    """(resource_type, resource_id, day, period) -> unit keys occupying it."""
    occ: dict[tuple[str, str, int, int], list[str]] = {}
    for key, pl in placements.items():
        if key == exclude:
            continue
        unit = problem.unit_by_key.get(key)
        if unit is None:
            continue
        for d, q in problem.grid.covered(pl.day, pl.period, unit.length):
            for rtype, rid in resource_keys(unit, pl.room_id):
                occ.setdefault((rtype, rid, d, q), []).append(key)
    return occ
