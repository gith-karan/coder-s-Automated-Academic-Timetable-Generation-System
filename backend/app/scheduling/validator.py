"""Independent checker of every mandatory rule (H-1 … H-8).

Single source of truth used by: (1) post-solve safety net, (2) manual edits, (3) the drag
"move options" heatmap, (4) the publish gate. It deliberately does not reuse the solver model, so a
solver bug can never silently produce an invalid timetable.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from app.scheduling.domain import Placement, Problem, SessionUnit, build_occupancy
from app.scheduling.timegrid import DAY_NAMES


@dataclass
class Violation:
    code: str
    severity: str  # HARD | SOFT
    message: str
    keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _who(problem: Problem, rtype: str, rid: str) -> str:
    if rtype == "faculty":
        f = problem.faculty.get(rid)
        return f.name if f else "Faculty"
    if rtype == "room":
        r = problem.rooms.get(rid)
        return f"Room {r.code}" if r else "Room"
    for g in problem.groups.values():
        if rid == g.id:
            return g.label
        if rid in g.batch_labels:
            return f"{g.label} / {g.batch_labels[rid]}"
    return rid


def check_unit(problem: Problem, unit: SessionUnit, pl: Placement) -> list[Violation]:
    """Rules that depend on a single placement only."""
    out: list[Violation] = []
    g = problem.grid
    where = g.slot_label((pl.day, pl.period))
    if not g.contiguous(pl.day, pl.period, unit.length):
        msg = (f"{unit.label} at {where} falls outside working hours or crosses a break"
               if unit.length > 1 else f"{unit.label} at {where} is outside working hours")
        out.append(Violation("OUTSIDE_WORKING_HOURS", "HARD", msg, [unit.key]))
        return out
    cov = g.covered(pl.day, pl.period, unit.length)
    blocked = problem.rules.group_blocked.get(unit.group_id)
    if blocked and any(s in blocked for s in cov):
        label = problem.rules.group_block_label.get(unit.group_id, "a blocked period")
        out.append(Violation("CLASS_BLOCKED", "HARD", f"{unit.audience} is not available at {where} ({label})",
                             [unit.key]))
    win = problem.rules.subject_windows.get(unit.subject_id)
    if win and not all(s in win.allowed for s in cov):
        out.append(Violation("OUTSIDE_SUBJECT_WINDOW", "HARD" if win.hard else "SOFT",
                             f"{unit.label} at {where} is outside its allowed time ({win.label})", [unit.key]))
    for fid in unit.faculty_ids:
        f = problem.faculty.get(fid)
        if f and not all(s in f.available for s in cov):
            out.append(Violation("FACULTY_UNAVAILABLE", "HARD",
                                 f"{f.name} is not available at {where} ({unit.label})", [unit.key]))
    room = problem.rooms.get(pl.room_id)
    if room is None:
        out.append(Violation("ROOM_MISSING", "HARD", f"{unit.label} has no valid room", [unit.key]))
    else:
        if room.capacity < unit.strength:
            out.append(Violation("ROOM_CAPACITY", "HARD",
                                 f"Room {room.code} seats {room.capacity} but {unit.audience} has {unit.strength} students",
                                 [unit.key]))
        if problem.room_reserved_against(unit, room):
            out.append(Violation("ROOM_RESERVED", "HARD",
                                 f"Room {room.code} is reserved for other programmes", [unit.key]))
        elif not problem.room_suitable(unit, room) and room.capacity >= unit.strength:
            need = f"a {unit.lab_type or 'laboratory'}" if unit.room_kind == "LAB" else "a classroom"
            out.append(Violation("ROOM_TYPE", "HARD", f"{unit.label} needs {need}; {room.code} is not suitable",
                                 [unit.key]))
        if not problem.room_free(room, pl.day, pl.period, unit.length):
            out.append(Violation("ROOM_UNAVAILABLE", "HARD", f"Room {room.code} is unavailable at {where}",
                                 [unit.key]))
    pin = problem.pins.get(unit.key)
    if pin and (pin.day, pin.period) != (pl.day, pl.period):
        out.append(Violation("FIXED_SESSION_MOVED", "HARD",
                             f"{unit.label} is {pin.reason} at {g.slot_label((pin.day, pin.period))}", [unit.key]))
    return out


def validate(problem: Problem, placements: dict[str, Placement], *, require_complete: bool = True) -> list[Violation]:
    out: list[Violation] = []
    units = problem.unit_by_key

    for key, pl in placements.items():
        unit = units.get(key)
        if unit is None:
            out.append(Violation("UNKNOWN_SESSION", "HARD",
                                 "A scheduled session no longer matches the current teaching requirements", [key]))
            continue
        out.extend(check_unit(problem, unit, pl))

    # H-3 / H-4: overlaps of faculty, rooms and student atoms
    occ = build_occupancy(problem, {k: v for k, v in placements.items() if k in units})
    seen: set[tuple] = set()
    for (rtype, rid, d, q), keys in occ.items():
        if len(keys) > 1:
            sig = (rtype, rid, tuple(sorted(keys)))
            if sig in seen:
                continue
            seen.add(sig)
            labels = ", ".join(units[k].subject_code for k in keys)
            noun = {"faculty": "is double-booked", "room": "is double-booked",
                    "atom": "has overlapping sessions"}[rtype]
            out.append(Violation(f"{rtype.upper()}_CLASH", "HARD",
                                 f"{_who(problem, rtype, rid)} {noun} at {problem.grid.slot_label((d, q))}: {labels}",
                                 sorted(keys)))

    # Daily limits
    fac_day: dict[tuple[str, int], int] = defaultdict(int)
    grp_day: dict[tuple[str, int], int] = defaultdict(int)
    for key, pl in placements.items():
        u = units.get(key)
        if not u:
            continue
        for f in u.faculty_ids:
            fac_day[(f, pl.day)] += u.length
        for a in u.atoms:
            grp_day[(a, pl.day)] += u.length
    for (fid, d), n in fac_day.items():
        lim = problem.faculty_daily_limit(fid)
        if lim and n > lim:
            out.append(Violation("FACULTY_DAILY_LIMIT", "HARD",
                                 f"{_who(problem, 'faculty', fid)} teaches {n} periods on "
                                 f"{DAY_NAMES[d]} (limit {lim})"))
    for g in problem.groups.values():
        lim = problem.group_daily_limit(g.id)
        if not lim:
            continue
        for d in problem.grid.days:
            n = max((grp_day.get((a, d), 0) for a in g.atoms), default=0)
            if n > lim:
                out.append(Violation("GROUP_DAILY_LIMIT", "HARD",
                                     f"{g.label} has {n} periods on {DAY_NAMES[d]} (limit {lim})"))

    # Custom rule: maximum consecutive teaching periods
    fac_slots: dict[tuple[str, int], set[int]] = defaultdict(set)
    for key, pl in placements.items():
        u = units.get(key)
        if u:
            for f in u.faculty_ids:
                fac_slots[(f, pl.day)].update(range(pl.period, pl.period + u.length))
    for (fid, d), ps in fac_slots.items():
        rule = problem.rules.consecutive_for(fid)
        if not rule:
            continue
        n, hard_rule, _ = rule
        run = best = 0
        for q in range(problem.grid.n_periods(d)):
            if q in ps and (run == 0 or problem.grid.contiguous(d, q - 1, 2)):
                run += 1
            else:
                run = 1 if q in ps else 0
            best = max(best, run)
        if best > n:
            out.append(Violation("FACULTY_CONSECUTIVE", "HARD" if hard_rule else "SOFT",
                                 f"{_who(problem, 'faculty', fid)} teaches {best} periods in a row on {DAY_NAMES[d]} "
                                 f"(rule: at most {n})"))

    # H-7: completeness
    if require_complete:
        missing = [u for u in problem.units if u.key not in placements]
        for u in missing:
            out.append(Violation("UNASSIGNED", "HARD", f"{u.label} is not scheduled", [u.key]))

    # Soft: spreading theory across days
    if problem.options.spread_mode != "OFF":
        per_day: dict[tuple, int] = defaultdict(int)
        for key, pl in placements.items():
            u = units.get(key)
            if u and u.kind == "THEORY":
                per_day[(u.family, pl.day)] += 1
        for (fam, _day), n in per_day.items():
            if n > 1:
                sev = "HARD" if problem.options.spread_mode == "HARD" else "SOFT"
                code = next(u.subject_code for u in problem.units if u.family == fam)
                out.append(Violation("SUBJECT_SAME_DAY", sev,
                                     f"{code} has {n} theory periods on the same day for one class"))
    return out


def hard(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.severity == "HARD"]
