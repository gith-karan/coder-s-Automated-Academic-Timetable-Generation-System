"""Database -> pure scheduling ``Problem`` (the only bridge between persistence and the engine)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academic import (
    Break, CalendarSettings, ConstraintMode, CustomRule, Faculty, FixedSession, Room, RuleKind, StudentGroup, Subject,
    SubjectKind,
)
from app.models.timetable import Timetable, TimetableEntry, TimetableStatus
from app.scheduling.domain import (
    CLASSROOM, LAB, FacultyInfo, GroupInfo, Pin, Placement, Problem, RoomInfo, Rules, SessionUnit, SubjectWindow,
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


def term_semesters(term: str | None, semesters: list[int] | None) -> list[int] | None:
    """ODD term = semesters I, III, V…; EVEN term = II, IV, VI… (explicit semesters win)."""
    if semesters:
        return semesters
    if term == "ODD":
        return [1, 3, 5, 7, 9, 11]
    if term == "EVEN":
        return [2, 4, 6, 8, 10, 12]
    return None


def load_rules(db: Session, grid: TimeGrid) -> Rules:
    rules = Rules()
    for r in db.execute(select(CustomRule).where(CustomRule.enabled.is_(True))).scalars():
        prm = r.params or {}
        hard = r.mode == ConstraintMode.HARD
        if r.kind == RuleKind.CLASS_BLOCK:
            gid = prm.get("group_id")
            slots = grid.slots_touching(_ranges(prm.get("ranges")))
            rules.group_blocked[gid] = rules.group_blocked.get(gid, frozenset()) | frozenset(slots)
            label = prm.get("label") or "blocked by a rule"
            prev = rules.group_block_label.get(gid)
            rules.group_block_label[gid] = f"{prev}; {label}" if prev and label not in prev else label
        elif r.kind == RuleKind.SUBJECT_WINDOW:
            days = prm.get("days") or grid.days
            ranges = [TimeRange(d, to_minutes(prm.get("start", "00:00")), to_minutes(prm.get("end", "23:59"))) for d in days]
            rules.subject_windows[prm.get("subject_id")] = SubjectWindow(
                frozenset(grid.slots_within(ranges)), hard, r.weight, r.note or "custom time window")
        elif r.kind == RuleKind.FACULTY_MAX_CONSECUTIVE:
            rules.max_consecutive[prm.get("faculty_id") or "*"] = (int(prm.get("max", 3)), hard, r.weight)
        elif r.kind == RuleKind.ROOM_RESERVED:
            rules.room_programmes[prm.get("room_id")] = frozenset(prm.get("programme_ids") or [])
    return rules


def build_problem(db: Session, *, programme_ids: list[str] | None = None, semesters: list[int] | None = None,
                  timetable: Timetable | None = None, keep_locked: bool = True, term: str | None = None) -> Problem:
    grid = load_grid(db)
    options = constraints.to_options(db)
    semesters = term_semesters(term, semesters)

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
                                 g.max_periods_per_day, g.home_room_id, g.programme_id)
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

    scope_errors = _scope_errors(db, groups_db, units, programme_ids, semesters, term)

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

    problem = Problem(grid, rooms, faculty, groups, units, pins, previous, options, warnings, load_rules(db, grid))
    problem.scope_errors = scope_errors
    return problem


ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def _scope_errors(db: Session, groups_db: list, units: list, programme_ids, semesters, term) -> list[dict]:
    """Plain-English reasons why the chosen scope has nothing to schedule."""
    from app.models.academic import Programme

    out: list[dict] = []
    progs = list(db.execute(select(Programme)).unique().scalars())
    in_scope = [p for p in progs if not programme_ids or p.id in programme_ids]
    which = f"{'the ' + term.lower() + ' term' if term else 'this selection'}"
    sem_txt = ", ".join(ROMAN[s] if s < len(ROMAN) else str(s) for s in (semesters or [])[:6])
    if not progs:
        out.append({"code": "NO_PROGRAMMES", "message": "No programmes exist yet. Add programmes and their classes first.",
                    "fix": {"page": "programmes"}})
        return out
    if not groups_db:
        have = []
        for p in in_scope:
            sems = sorted({g.semester for g in p.groups})
            have.append(f"{p.code}: " + (", ".join(f"Sem {ROMAN[s] if s < len(ROMAN) else s}" for s in sems) if sems else "no classes"))
        out.append({"code": "NO_CLASSES_IN_SCOPE",
                    "message": f"No class sections match {which}" + (f" (semesters {sem_txt})" if sem_txt else "") +
                               ". Existing classes — " + "; ".join(have) +
                               ". Add a class under Programmes → Class sections, or choose the other term.",
                    "fix": {"page": "programmes"}})
        return out
    subj_q = select(Subject)
    if programme_ids:
        subj_q = subj_q.where(Subject.programme_id.in_(programme_ids))
    subjects = list(db.execute(subj_q).unique().scalars())
    empty = []
    for g in groups_db:
        if not any(s.programme_id == g.programme_id and s.semester == g.semester for s in subjects):
            empty.append(g.label)
    if not units:
        out.append({"code": "NO_SUBJECTS_FOR_CLASSES",
                    "message": "There is nothing to schedule: no subjects are defined for " + ", ".join(empty[:6]) +
                               ". Add subjects for these programmes and semesters under Subjects.",
                    "fix": {"page": "subjects"}})
    elif empty:
        out.append({"code": "CLASS_WITHOUT_SUBJECTS", "severity": "WARNING",
                    "message": f"{', '.join(empty[:6])} {'has' if len(empty) == 1 else 'have'} no subjects, so "
                               f"{'it' if len(empty) == 1 else 'they'} will get an empty timetable.",
                    "fix": {"page": "subjects"}})
    if not db.execute(select(Faculty.id)).first():
        out.append({"code": "NO_FACULTY_AT_ALL", "message": "No faculty members exist yet. Add faculty first.",
                    "fix": {"page": "faculty"}})
    if not db.execute(select(Room.id).where(Room.is_active.is_(True))).first():
        out.append({"code": "NO_ROOMS_AT_ALL", "message": "No active classrooms or labs exist. Add rooms first.",
                    "fix": {"page": "rooms"}})
    return out
