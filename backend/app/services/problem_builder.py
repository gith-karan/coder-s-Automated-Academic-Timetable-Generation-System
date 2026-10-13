"""Database -> pure scheduling ``Problem`` (the only bridge between persistence and the engine)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academic import Break, CalendarSettings, Faculty, FixedSession, Room, StudentGroup, Subject, SubjectKind
from app.models.timetable import Timetable, TimetableEntry, TimetableStatus
from app.scheduling.domain import (
    CLASSROOM, LAB, FacultyInfo, GroupInfo, Pin, Placement, Problem, RoomInfo, SessionUnit,
)
from app.scheduling.timegrid import BreakSpec, Slot, TimeGrid, TimeRange, to_minutes
from app.services import constraints


def load_calendar(db: Session) -> CalendarSettings:
    cal = db.get(CalendarSettings, 1)
    if cal is None:
        cal = CalendarSettings(id=1)
        db.add(cal)
        db.flush()
    return cal


def load_grid(db: Session) -> TimeGrid:
    cal = load_calendar(db)
    breaks = [BreakSpec(b.name, to_minutes(b.start_time), to_minutes(b.end_time),
                        frozenset(b.days) if b.days else None) for b in db.execute(select(Break)).scalars()]
    return TimeGrid(list(cal.working_days), to_minutes(cal.day_start), to_minutes(cal.day_end),
                    cal.period_minutes, breaks)


def _ranges(items: list[dict] | None) -> list[TimeRange]:
    return [TimeRange.parse(r) for r in (items or [])]


def faculty_slots(grid: TimeGrid, f: Faculty) -> tuple[set[Slot], set[Slot]]:
    av = f.availability or {}
    all_slots = set(grid.all_slots())
    available = grid.slots_within(_ranges(av["available"])) if av.get("available") is not None else set(all_slots)
    blocked = grid.slots_touching(_ranges(av.get("unavailable")) + _ranges(av.get("commitments")))
    preferred = grid.slots_within(_ranges(av.get("preferred")))
    return (available - blocked) & all_slots, preferred & all_slots


def session_key(subject_id: str, group_id: str, batch_id: str | None, n: int) -> str:
    return f"{subject_id}|{group_id}|{batch_id or '-'}|{n}"


def build_problem(db: Session, *, programme_ids: list[str] | None = None, semesters: list[int] | None = None,
                  timetable: Timetable | None = None, keep_locked: bool = True) -> Problem:
    grid = load_grid(db)
    options = constraints.to_options(db)

    gq = select(StudentGroup)
    if programme_ids:
        gq = gq.where(StudentGroup.programme_id.in_(programme_ids))
    if semesters:
        gq = gq.where(StudentGroup.semester.in_(semesters))
    groups_db = list(db.execute(gq).unique().scalars())
    group_ids = {g.id for g in groups_db}

    # Faculty/rooms already committed in OTHER published timetables (e.g. other programmes) are blocked.
    external: dict[tuple[str, str], set[Slot]] = defaultdict(set)
    published = db.execute(select(TimetableEntry).join(Timetable).where(
        Timetable.status == TimetableStatus.PUBLISHED, TimetableEntry.day.is_not(None))).scalars()
    for e in published:
        if e.group_id in group_ids or (timetable is not None and e.timetable_id == timetable.id):
            continue
        cov = grid.covered(e.day, e.start_period, e.length)
        for fid in e.faculty_ids or []:
            external[("faculty", fid)].update(cov)
        if e.room_id:
            external[("room", e.room_id)].update(cov)

    rooms: dict[str, RoomInfo] = {}
    for r in db.execute(select(Room).where(Room.is_active.is_(True))).unique().scalars():
        blocked = grid.slots_touching(_ranges(r.unavailable)) | external.get(("room", r.id), set())
        rooms[r.id] = RoomInfo(r.id, r.code, r.name, r.kind.value, r.lab_type.name if r.lab_type else None,
                               r.capacity, frozenset(blocked))

    faculty: dict[str, FacultyInfo] = {}
    for f in db.execute(select(Faculty)).scalars():
        avail, pref = faculty_slots(grid, f)
        avail -= external.get(("faculty", f.id), set())
        faculty[f.id] = FacultyInfo(f.id, f.code, f.name, frozenset(avail), frozenset(pref),
                                    f.max_periods_per_day, f.max_periods_per_week)

    warnings: list[dict] = []
    groups: dict[str, GroupInfo] = {}
    by_prog_sem: dict[tuple[str, int], list[StudentGroup]] = defaultdict(list)
    for g in groups_db:
        atoms = tuple(b.id for b in g.batches) or (g.id,)
        groups[g.id] = GroupInfo(g.id, g.label, g.strength, atoms, {b.id: b.name for b in g.batches},
                                 g.max_periods_per_day, g.home_room_id)
        by_prog_sem[(g.programme_id, g.semester)].append(g)
        if g.batches and sum(b.strength for b in g.batches) != g.strength:
            warnings.append({"code": "BATCH_STRENGTH_MISMATCH",
                             "message": f"Batch strengths of {g.label} add up to {sum(b.strength for b in g.batches)}, "
                                        f"but the class strength is {g.strength}.",
                             "entities": [{"type": "group", "id": g.id, "label": g.label}],
                             "fix": {"page": "programmes", "id": g.programme_id}})

    units: list[SessionUnit] = []
    sq = select(Subject)
    if programme_ids:
        sq = sq.where(Subject.programme_id.in_(programme_ids))
    if semesters:
        sq = sq.where(Subject.semester.in_(semesters))
    for s in db.execute(sq).unique().scalars():
        fids = tuple(sorted(f.id for f in s.faculty))
        targets = by_prog_sem.get((s.programme_id, s.semester), [])
        if not targets:
            warnings.append({"code": "SUBJECT_WITHOUT_CLASS",
                             "message": f"Subject {s.code} has no class section for {s.programme.code} semester "
                                        f"{s.semester}, so it will not be scheduled.",
                             "entities": [{"type": "subject", "id": s.id, "label": s.code}],
                             "fix": {"page": "programmes", "id": s.programme_id}})
        for g in targets:
            info = groups[g.id]
            if s.kind == SubjectKind.THEORY:
                for n in range(s.periods_per_week):
                    units.append(SessionUnit(session_key(s.id, g.id, None, n), s.id, s.code, s.name, "THEORY",
                                             g.id, None, info.label, g.strength, 1, fids, info.atoms, CLASSROOM,
                                             None, n))
            else:
                audiences = [(b.id, f"{info.label} / {b.name}", b.strength, (b.id,)) for b in g.batches] or \
                            [(None, info.label, g.strength, info.atoms)]
                for bid, label, strength, atoms in audiences:
                    for n in range(s.sessions_per_week):
                        units.append(SessionUnit(session_key(s.id, g.id, bid, n), s.id, s.code, s.name, "PRACTICAL",
                                                 g.id, bid, label, strength, s.consecutive_periods, fids, atoms, LAB,
                                                 s.lab_type.name if s.lab_type else None, n))

    unit_keys = {u.key for u in units}
    pins: dict[str, Pin] = {}
    previous: dict[str, Placement] = {}
    if timetable is not None:
        for e in timetable.entries:
            if e.session_key in unit_keys and e.day is not None and e.room_id:
                previous[e.session_key] = Placement(e.session_key, e.day, e.start_period, e.room_id)
                if keep_locked and e.locked:
                    pins[e.session_key] = Pin(e.session_key, e.day, e.start_period, e.room_id, "locked")

    # Fixed sessions: pin the first not-yet-pinned unit of the matching (subject, class, batch) family.
    for fs in db.execute(select(FixedSession)).scalars():
        if fs.group_id not in groups:
            continue
        n = 0
        while session_key(fs.subject_id, fs.group_id, fs.batch_id, n) in pins:
            n += 1
        key = session_key(fs.subject_id, fs.group_id, fs.batch_id, n)
        if key in unit_keys:
            pins[key] = Pin(key, fs.day, fs.start_period, fs.room_id, "fixed")

    return Problem(grid, rooms, faculty, groups, units, pins, previous, options, warnings)
