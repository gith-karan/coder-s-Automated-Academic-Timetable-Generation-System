"""Timetable use cases: save solver output, views, manual edits, locking, validation, publishing, diff."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, bad_request, conflict, not_found
from app.models.academic import Faculty, Room, StudentGroup, Subject
from app.models.timetable import Timetable, TimetableEntry, TimetableStatus
from app.scheduling.domain import Placement, Problem, build_occupancy
from app.scheduling.engine import Outcome
from app.scheduling.scoring import score
from app.scheduling.timegrid import DAY_SHORT, fmt
from app.scheduling.validator import Violation, hard, validate
from app.services.problem_builder import build_problem, load_grid


def get_timetable(db: Session, tid: str) -> Timetable:
    tt = db.get(Timetable, tid)
    if tt is None:
        raise not_found("Timetable")
    return tt


def problem_for(db: Session, tt: Timetable, *, keep_locked: bool = True) -> Problem:
    return build_problem(db, programme_ids=tt.programme_ids or None, semesters=tt.semesters or None,
                         timetable=tt, keep_locked=keep_locked)


def placements_of(tt: Timetable) -> dict[str, Placement]:
    return {e.session_key: Placement(e.session_key, e.day, e.start_period, e.room_id)
            for e in tt.entries if e.day is not None and e.start_period is not None and e.room_id}


def ensure_editable(tt: Timetable) -> None:
    if tt.status != TimetableStatus.DRAFT:
        raise conflict(f"This timetable is {tt.status.value.replace('_', ' ').lower()} and cannot be edited. "
                       "Duplicate it to make changes.")


def save_outcome(db: Session, tt: Timetable, problem: Problem, outcome: Outcome) -> None:
    """Replace the timetable's entries with the engine's result (locked entries are kept as pinned)."""
    existing = {e.session_key: e for e in tt.entries}
    keep = set()
    for u in problem.units:
        pl = outcome.placements.get(u.key)
        e = existing.get(u.key)
        if e is None:
            e = TimetableEntry(timetable_id=tt.id, session_key=u.key)
            tt.entries.append(e)
        e.subject_id, e.group_id, e.batch_id = u.subject_id, u.group_id, u.batch_id
        e.faculty_ids, e.length = list(u.faculty_ids), u.length
        if pl is not None:
            e.day, e.start_period, e.room_id = pl.day, pl.period, pl.room_id
        elif not e.locked:
            e.day = e.start_period = e.room_id = None
        keep.add(u.key)
    for key, e in existing.items():
        if key not in keep:
            tt.entries.remove(e)
    tt.is_complete = outcome.status == "SUCCESS"
    tt.quality_score = outcome.quality["quality"] if outcome.quality else None
    tt.row_version += 1


# ------------------------------------------------------------------ views
def _lookup(db: Session, tt: Timetable) -> dict:
    subj_ids = {e.subject_id for e in tt.entries}
    grp_ids = {e.group_id for e in tt.entries}
    fac_ids = {f for e in tt.entries for f in (e.faculty_ids or [])}
    room_ids = {e.room_id for e in tt.entries if e.room_id}
    subjects = {s.id: s for s in db.execute(select(Subject).where(Subject.id.in_(subj_ids))).unique().scalars()} if subj_ids else {}
    groups = {g.id: g for g in db.execute(select(StudentGroup).where(StudentGroup.id.in_(grp_ids))).unique().scalars()} if grp_ids else {}
    faculty = {f.id: f for f in db.execute(select(Faculty).where(Faculty.id.in_(fac_ids))).scalars()} if fac_ids else {}
    rooms = {r.id: r for r in db.execute(select(Room).where(Room.id.in_(room_ids))).unique().scalars()} if room_ids else {}
    return {"subjects": subjects, "groups": groups, "faculty": faculty, "rooms": rooms}


def entry_dto(e: TimetableEntry, lk: dict, subject_colors: dict[str, int]) -> dict:
    s = lk["subjects"].get(e.subject_id)
    g = lk["groups"].get(e.group_id)
    batch = next((b for b in (g.batches if g else []) if b.id == e.batch_id), None)
    room = lk["rooms"].get(e.room_id) if e.room_id else None
    return {
        "id": e.id, "session_key": e.session_key, "day": e.day, "start_period": e.start_period, "length": e.length,
        "locked": e.locked,
        "subject": {"id": e.subject_id, "code": s.code if s else "?", "name": s.name if s else "?",
                    "kind": s.kind.value if s else "THEORY"},
        "group": {"id": e.group_id, "label": g.label if g else "?",
                  "programme_id": g.programme_id if g else None, "semester": g.semester if g else None},
        "batch": {"id": batch.id, "name": batch.name} if batch else None,
        "faculty": [{"id": fid, "name": lk["faculty"][fid].name, "code": lk["faculty"][fid].code}
                    for fid in (e.faculty_ids or []) if fid in lk["faculty"]],
        "room": {"id": room.id, "code": room.code, "name": room.name} if room else None,
        "color": subject_colors.get(e.subject_id, 0),
    }


def view(db: Session, tt: Timetable, *, by: str | None = None, ref: str | None = None) -> dict:
    """Entries filtered for a programme/class, faculty member or room, plus the period grid."""
    grid = load_grid(db)
    lk = _lookup(db, tt)
    colors = {sid: i % 12 for i, sid in enumerate(sorted(lk["subjects"], key=lambda k: lk["subjects"][k].code))}
    entries = tt.entries
    if by and ref:
        if by == "group":
            entries = [e for e in entries if e.group_id == ref]
        elif by == "programme":
            entries = [e for e in entries if lk["groups"].get(e.group_id) and lk["groups"][e.group_id].programme_id == ref]
        elif by == "faculty":
            entries = [e for e in entries if ref in (e.faculty_ids or [])]
        elif by == "room":
            entries = [e for e in entries if e.room_id == ref]
        else:
            raise bad_request("view must be one of: group, programme, faculty, room")
    placed = [entry_dto(e, lk, colors) for e in entries if e.day is not None]
    unplaced = [entry_dto(e, lk, colors) for e in entries if e.day is None]
    return {"timetable": timetable_summary(tt), "grid": grid.to_dict(), "entries": placed, "unassigned": unplaced}


def timetable_summary(tt: Timetable) -> dict:
    placed = sum(1 for e in tt.entries if e.day is not None)
    return {"id": tt.id, "name": tt.name, "status": tt.status.value, "quality_score": tt.quality_score,
            "is_complete": tt.is_complete, "row_version": tt.row_version, "programme_ids": tt.programme_ids,
            "semesters": tt.semesters, "total_sessions": len(tt.entries), "scheduled": placed,
            "unassigned": len(tt.entries) - placed, "locked": sum(1 for e in tt.entries if e.locked),
            "created_at": tt.created_at.isoformat() if tt.created_at else None,
            "updated_at": tt.updated_at.isoformat() if tt.updated_at else None,
            "submitted_at": tt.submitted_at.isoformat() if tt.submitted_at else None,
            "published_at": tt.published_at.isoformat() if tt.published_at else None,
            "review_comment": tt.review_comment, "parent_id": tt.parent_id, "last_run_id": tt.last_run_id}


# ------------------------------------------------------------------ editing
def _entry(tt: Timetable, entry_id: str) -> TimetableEntry:
    e = next((x for x in tt.entries if x.id == entry_id), None)
    if e is None:
        raise not_found("Session")
    return e


def check_move(problem: Problem, placements: dict[str, Placement], key: str, day: int, period: int,
               room_id: str) -> list[Violation]:
    unit = problem.unit_by_key.get(key)
    if unit is None:
        return [Violation("UNKNOWN_SESSION", "HARD", "This session no longer matches the teaching requirements.", [key])]
    trial = dict(placements)
    trial[key] = Placement(key, day, period, room_id)
    return [v for v in hard(validate(problem, trial, require_complete=False)) if key in v.keys or not v.keys]


def move_entry(db: Session, tt: Timetable, entry_id: str, *, day: int, start_period: int, room_id: str | None,
               expected_version: int | None) -> tuple[TimetableEntry, list[Violation]]:
    ensure_editable(tt)
    if expected_version is not None and expected_version != tt.row_version:
        raise AppError(409, "stale", "Someone else changed this timetable. Reload to see the latest version.")
    e = _entry(tt, entry_id)
    if e.locked:
        raise conflict("This session is locked. Unlock it before moving.")
    problem = problem_for(db, tt)
    placements = placements_of(tt)
    target_room = room_id or e.room_id
    if target_room is None:
        opts = move_options(db, tt, entry_id, problem=problem)
        cell = next((c for c in opts["cells"] if c["day"] == day and c["period"] == start_period), None)
        target_room = cell["best_room_id"] if cell else None
        if target_room is None:
            raise conflict("No suitable room is free at that time.", violations=[])
    violations = check_move(problem, placements, e.session_key, day, start_period, target_room)
    if violations:
        raise AppError(409, "conflict", violations[0].message, extra={"violations": [v.to_dict() for v in violations]})
    e.day, e.start_period, e.room_id = day, start_period, target_room
    placements[e.session_key] = Placement(e.session_key, day, start_period, target_room)
    tt.is_complete = not hard(validate(problem, placements))
    tt.quality_score = score(problem, placements)["quality"]
    tt.row_version += 1
    return e, violations


def move_options(db: Session, tt: Timetable, entry_id: str, *, problem: Problem | None = None) -> dict:
    """Feasibility heatmap for dragging one session: every (day, period) cell with status and reason."""
    e = _entry(tt, entry_id)
    problem = problem or problem_for(db, tt)
    unit = problem.unit_by_key.get(e.session_key)
    if unit is None:
        raise conflict("This session no longer matches the teaching requirements; regenerate the timetable.")
    placements = placements_of(tt)
    occ = build_occupancy(problem, placements, exclude=e.session_key)
    labels = {k: problem.unit_by_key[k].subject_code for k in problem.unit_by_key}
    grid = problem.grid
    rooms = problem.rooms_for(unit)
    cells = []
    for d in grid.days:
        for p in range(grid.n_periods(d)):
            reasons: list[str] = []
            if not grid.contiguous(d, p, unit.length):
                cells.append({"day": d, "period": p, "status": "blocked", "reasons": ["Crosses a break or end of day"],
                              "best_room_id": None})
                continue
            cov = grid.covered(d, p, unit.length)
            for fid in unit.faculty_ids:
                f = problem.faculty.get(fid)
                if f and not all(c in f.available for c in cov):
                    reasons.append(f"{f.name} unavailable")
                busy = {k for c in cov for k in occ.get(("faculty", fid, *c), [])}
                if busy and f:
                    reasons.append(f"{f.name} busy — {', '.join(sorted(labels[k] for k in busy))}")
            for a in unit.atoms:
                busy = {k for c in cov for k in occ.get(("atom", a, *c), [])}
                if busy:
                    reasons.append(f"Students busy — {', '.join(sorted(labels[k] for k in busy))}")
                    break
            free_rooms = [r for r in rooms if problem.room_free(r, d, p, unit.length)
                          and not any(occ.get(("room", r.id, *c)) for c in cov)]
            if not free_rooms:
                reasons.append("No suitable room free")
            best = None
            if free_rooms:
                cur = next((r for r in free_rooms if r.id == e.room_id), None)
                best = (cur or free_rooms[0]).id
            pin = problem.pins.get(unit.key)
            if pin and pin.reason == "fixed" and (pin.day, pin.period) != (d, p):
                reasons.append("Fixed session")
            soft = []
            if not reasons:
                for fid in unit.faculty_ids:
                    f = problem.faculty.get(fid)
                    if f and f.preferred and not all(c in f.preferred for c in cov):
                        soft.append(f"Outside {f.name}'s preferred time")
            cells.append({"day": d, "period": p,
                          "status": "blocked" if reasons else ("warning" if soft else "ok"),
                          "reasons": reasons or soft, "best_room_id": best,
                          "current": (e.day, e.start_period) == (d, p)})
    return {"entry_id": entry_id, "length": unit.length, "cells": cells,
            "rooms": [{"id": r.id, "code": r.code, "capacity": r.capacity} for r in rooms]}


def set_lock(tt: Timetable, entry_ids: list[str], locked: bool) -> int:
    ensure_editable(tt)
    n = 0
    for e in tt.entries:
        if e.id in entry_ids and e.day is not None and e.locked != locked:
            e.locked = locked
            n += 1
    tt.row_version += 1
    return n


def validate_timetable(db: Session, tt: Timetable) -> dict:
    problem = problem_for(db, tt)
    placements = placements_of(tt)
    violations = validate(problem, placements)
    q = score(problem, placements)
    return {"valid": not hard(violations), "violations": [v.to_dict() for v in violations], "score": q,
            "summary": timetable_summary(tt)}


def content_hash(tt: Timetable) -> str:
    rows = sorted((e.session_key, e.day, e.start_period, e.room_id, tuple(e.faculty_ids or [])) for e in tt.entries)
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()


def diff(a: Timetable, b: Timetable) -> dict:
    ea = {e.session_key: e for e in a.entries}
    eb = {e.session_key: e for e in b.entries}
    moved, added, removed = [], [], []
    for k, e in eb.items():
        o = ea.get(k)
        if o is None:
            added.append(k)
        elif (o.day, o.start_period, o.room_id) != (e.day, e.start_period, e.room_id):
            moved.append({"key": k, "from": [o.day, o.start_period, o.room_id], "to": [e.day, e.start_period, e.room_id]})
    removed = [k for k in ea if k not in eb]
    return {"moved": moved, "added": added, "removed": removed,
            "unchanged": len(eb) - len(moved) - len(added)}


def slot_text(problem: Problem, day: int, period: int) -> str:
    p = problem.grid.period(day, period)
    return f"{DAY_SHORT[day]} {fmt(p.start)}" if p else f"{DAY_SHORT[day]} P{period + 1}"


def faculty_load(problem: Problem, placements: dict[str, Placement]) -> dict[str, int]:
    load: dict[str, int] = defaultdict(int)
    for k in placements:
        u = problem.unit_by_key.get(k)
        if u:
            for f in u.faculty_ids:
                load[f] += u.length
    return load
