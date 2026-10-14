"""Layer-2 diagnostics: fast counting checks that explain most impossible inputs in plain English
before the solver runs. Every diagnostic has a stable code, the entities involved, and a
``fix`` hint the UI turns into a "Fix →" link.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from app.scheduling.domain import LAB, Problem, SessionUnit


@dataclass
class Diagnostic:
    code: str
    severity: str  # ERROR blocks generation, WARNING does not
    message: str
    entities: list[dict] = field(default_factory=list)  # [{type, id, label}]
    sessions: list[str] = field(default_factory=list)
    fix: dict | None = None  # {"page": "faculty", "id": "...", "tab": "availability"}

    def to_dict(self) -> dict:
        return asdict(self)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _requirement_text(units: list[SessionUnit]) -> str:
    u = units[0]
    if u.kind == "THEORY":
        return f"{_plural(len(units), 'weekly period')}"
    return f"{_plural(len(units), 'weekly session')} of {u.length} consecutive periods"


def run_prechecks(problem: Problem) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    grid = problem.grid
    total_slots = len(grid.all_slots())
    fac = problem.faculty

    out.extend(problem_warnings(problem))
    for e in problem.scope_errors:
        out.append(Diagnostic(e["code"], e.get("severity", "ERROR"), e["message"], fix=e.get("fix")))
    if any(e.get("severity", "ERROR") == "ERROR" for e in problem.scope_errors):
        return out

    if total_slots == 0:
        out.append(Diagnostic("NO_PERIODS", "ERROR",
                              "The academic calendar produces no teaching periods. Check working days, hours and breaks.",
                              fix={"page": "calendar"}))
        return out

    families: dict[tuple, list[SessionUnit]] = defaultdict(list)
    for u in problem.units:
        families[u.family].append(u)

    largest_block = grid.longest_block()
    for fam_units in families.values():
        u = fam_units[0]
        subj_ent = {"type": "subject", "id": u.subject_id, "label": u.subject_code}
        what = "Practical" if u.kind == "PRACTICAL" else "Subject"
        keys = [x.key for x in fam_units]

        # -- faculty assigned?
        known = [f for f in u.faculty_ids if f in fac]
        if not known:
            out.append(Diagnostic("NO_FACULTY", "ERROR",
                                  f"{what} {u.subject_code} ({u.audience}) has no faculty member assigned.",
                                  [subj_ent], keys, {"page": "subjects", "id": u.subject_id}))
            continue

        # -- session longer than any break-free block
        if u.length > largest_block:
            out.append(Diagnostic("SESSION_TOO_LONG", "ERROR",
                                  f"Practical {u.subject_code} needs {u.length} consecutive periods, but the longest "
                                  f"break-free block in the day is only {largest_block} periods.",
                                  [subj_ent], keys, {"page": "subjects", "id": u.subject_id}))
            continue

        # -- the PS example: "Subject X requires N periods, but faculty is available for only M"
        need = len(fam_units) * u.length
        for fid in known:
            f = fac[fid]
            have = len(f.available)
            if have < need:
                out.append(Diagnostic(
                    "FACULTY_AVAIL_LT_REQUIRED", "ERROR",
                    f"{what} {u.subject_code} requires {_requirement_text(fam_units)} for {u.audience}, "
                    f"but its assigned faculty member {f.name} is available for only {_plural(have, 'period')}.",
                    [subj_ent, {"type": "faculty", "id": f.id, "label": f.name}], keys,
                    {"page": "faculty", "id": f.id, "tab": "availability"}))

        # -- rooms of the right kind and size
        if not problem.rooms_for(u):
            if u.room_kind == LAB:
                same_type = [r for r in problem.rooms.values()
                             if r.kind == LAB and (u.lab_type is None or r.lab_type == u.lab_type)]
                if not same_type:
                    msg = (f"Practical {u.subject_code} requires a {u.lab_type or 'laboratory'}, "
                           f"but no such laboratory is available.")
                    code = "NO_LAB_OF_TYPE"
                else:
                    biggest = max(r.capacity for r in same_type)
                    msg = (f"Practical {u.subject_code} for {u.audience} has {u.strength} students, but the largest "
                           f"{u.lab_type or 'laboratory'} seats only {biggest}. Split the class into smaller batches "
                           f"or add a larger lab.")
                    code = "NO_LAB_CAPACITY"
                out.append(Diagnostic(code, "ERROR", msg, [subj_ent], keys, {"page": "rooms"}))
            else:
                classrooms = [r.capacity for r in problem.rooms.values() if r.kind == "CLASSROOM"]
                biggest = max(classrooms, default=0)
                out.append(Diagnostic("NO_ROOM_FOR_STRENGTH", "ERROR",
                                      f"{u.audience} has {u.strength} students, but the largest classroom seats only "
                                      f"{biggest}.", [subj_ent], keys, {"page": "rooms"}))
            continue

        starts = problem.starts_for(u)
        if not starts and (problem.rules.group_blocked.get(u.group_id) or u.subject_id in problem.rules.subject_windows):
            out.append(Diagnostic("NO_TIME_WINDOW", "ERROR",
                                  f"{what} {u.subject_code} ({u.audience}) has no possible period: the custom rules for "
                                  f"this class/subject leave no time when its faculty is also available.",
                                  [subj_ent], keys, {"page": "constraints"}))
            continue
        if not starts:
            names = ", ".join(fac[f].name for f in known)
            if u.length > 1:
                msg = (f"Practical {u.subject_code} needs {u.length} consecutive periods, but {names} never has "
                       f"{u.length} consecutive free periods within working hours.")
            else:
                msg = f"{what} {u.subject_code}: {names} has no available period within working hours."
            out.append(Diagnostic("NO_CONSECUTIVE_WINDOW" if u.length > 1 else "NO_TIME_WINDOW", "ERROR", msg,
                                  [subj_ent], keys, {"page": "faculty", "id": known[0], "tab": "availability"}))
            continue

        # -- a time window exists, but every suitable room is blocked at all of them
        if not any(problem.room_free(r, d, p, u.length) for (d, p) in starts for r in problem.rooms_for(u)):
            out.append(Diagnostic("NO_ROOM_WHEN_FACULTY_FREE", "ERROR",
                                  f"{what} {u.subject_code}: no suitable room is free at any time its faculty is available.",
                                  [subj_ent], keys, {"page": "rooms"}))

        # -- distinct days needed when spreading is mandatory
        if u.kind == "THEORY" and problem.options.spread_mode == "HARD":
            days = {d for d, _ in starts}
            if len(fam_units) > len(days):
                out.append(Diagnostic("SPREAD_IMPOSSIBLE", "ERROR",
                                      f"Subject {u.subject_code} needs {len(fam_units)} periods on different days, but its "
                                      f"faculty is available on only {_plural(len(days), 'day')}.",
                                      [subj_ent], keys, {"page": "constraints"}))

    # -- faculty total load vs availability / limits
    load: dict[str, int] = defaultdict(int)
    load_units: dict[str, list[str]] = defaultdict(list)
    for u in problem.units:
        for f in u.faculty_ids:
            load[f] += u.length
            load_units[f].append(u.key)
    for fid, n in load.items():
        f = fac.get(fid)
        if not f:
            continue
        ent = [{"type": "faculty", "id": f.id, "label": f.name}]
        fix = {"page": "faculty", "id": f.id, "tab": "availability"}
        if n > len(f.available):
            out.append(Diagnostic("FACULTY_OVERLOADED", "ERROR",
                                  f"{f.name} is assigned {_plural(n, 'period')} per week but is available for only "
                                  f"{len(f.available)}.", ent, load_units[fid], fix))
        if f.max_per_week and n > f.max_per_week:
            out.append(Diagnostic("FACULTY_WEEKLY_LIMIT", "ERROR",
                                  f"{f.name} is assigned {_plural(n, 'period')} per week, above their weekly limit of "
                                  f"{f.max_per_week}.", ent, load_units[fid], fix))
        lim = problem.faculty_daily_limit(fid)
        if lim:
            days_avail = len({d for d, _ in f.available})
            if n > lim * days_avail:
                out.append(Diagnostic("FACULTY_DAILY_LIMIT", "ERROR",
                                      f"{f.name} needs {_plural(n, 'period')} per week, but a limit of {lim} per day over "
                                      f"{_plural(days_avail, 'available day')} allows at most {lim * days_avail}.",
                                      ent, load_units[fid], fix))

    # -- student atom load
    atom_load: dict[str, int] = defaultdict(int)
    for u in problem.units:
        for a in u.atoms:
            atom_load[a] += u.length
    for g in problem.groups.values():
        worst = max((atom_load.get(a, 0) for a in g.atoms), default=0)
        free = total_slots - len(problem.rules.group_blocked.get(g.id, ()))
        if worst > free:
            out.append(Diagnostic("GROUP_OVERLOADED", "ERROR",
                                  f"{g.label} needs {worst} teaching periods per week, but only {free} periods are "
                                  f"available to it (calendar and custom rules).",
                                  [{"type": "group", "id": g.id, "label": g.label}], fix={"page": "constraints"}))
        lim = problem.group_daily_limit(g.id)
        if lim and worst > lim * len(grid.days):
            out.append(Diagnostic("GROUP_DAILY_LIMIT", "ERROR",
                                  f"{g.label} needs {worst} periods per week, but the daily limit of {lim} allows at most "
                                  f"{lim * len(grid.days)}.", [{"type": "group", "id": g.id, "label": g.label}],
                                  fix={"page": "constraints"}))

    # -- room-type supply vs demand (pigeonhole)
    demand: dict[str, int] = defaultdict(int)
    for u in problem.units:
        if u.room_kind == LAB:
            demand[u.lab_type or "Any laboratory"] += u.length
    for lab_type, need in demand.items():
        labs = [r for r in problem.rooms.values() if r.kind == LAB and (lab_type == "Any laboratory" or r.lab_type == lab_type)]
        supply = sum(total_slots - len(r.blocked) for r in labs)
        if labs and need > supply:
            out.append(Diagnostic("LAB_TYPE_OVERSUBSCRIBED", "ERROR",
                                  f"Practicals need {need} {lab_type} periods per week, but the {len(labs)} "
                                  f"{lab_type}(s) offer only {supply}.", fix={"page": "rooms"}))
    theory_need = sum(u.length for u in problem.units if u.room_kind != LAB)
    classrooms = [r for r in problem.rooms.values() if r.kind == "CLASSROOM"]
    supply = sum(total_slots - len(r.blocked) for r in classrooms)
    if classrooms and theory_need > supply and not problem.options.allow_theory_in_lab:
        out.append(Diagnostic("CLASSROOMS_OVERSUBSCRIBED", "ERROR",
                              f"Theory needs {theory_need} classroom periods per week, but classrooms offer only {supply}.",
                              fix={"page": "rooms"}))

    out.extend(_check_pins(problem))
    return out


def _check_pins(problem: Problem) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    units = problem.unit_by_key
    grid = problem.grid
    occupied: dict[tuple, str] = {}
    for key, pin in problem.pins.items():
        u = units.get(key)
        if u is None:
            continue
        where = grid.slot_label((pin.day, pin.period))
        ent = [{"type": "subject", "id": u.subject_id, "label": u.subject_code}]
        if not grid.contiguous(pin.day, pin.period, u.length):
            out.append(Diagnostic("FIXED_SESSION_INVALID", "ERROR",
                                  f"{u.label} is fixed at {where}, which is outside working hours or crosses a break.",
                                  ent, [key], {"page": "constraints"}))
            continue
        if not problem.time_ok_for_faculty(u, pin.day, pin.period):
            out.append(Diagnostic("FIXED_SESSION_INVALID", "ERROR",
                                  f"{u.label} is fixed at {where}, but its faculty member is not available then.",
                                  ent, [key], {"page": "constraints"}))
        if pin.room_id:
            room = problem.rooms.get(pin.room_id)
            if room is None or not problem.room_suitable(u, room):
                out.append(Diagnostic("FIXED_SESSION_INVALID", "ERROR",
                                      f"{u.label} is fixed to a room that is unsuitable for it.", ent, [key],
                                      {"page": "constraints"}))
        for slot in grid.covered(pin.day, pin.period, u.length):
            res = [("faculty", f) for f in u.faculty_ids] + [("atom", a) for a in u.atoms]
            if pin.room_id:
                res.append(("room", pin.room_id))
            for r in res:
                other = occupied.get((r, slot))
                if other and other != key:
                    o = units[other]
                    out.append(Diagnostic("FIXED_SESSION_CONFLICT", "ERROR",
                                          f"Fixed sessions {u.label} and {o.label} overlap at {grid.slot_label(slot)}.",
                                          ent, [key, other], {"page": "constraints"}))
                occupied[(r, slot)] = key
    return out


def problem_warnings(problem: Problem) -> list[Diagnostic]:
    return [Diagnostic(w["code"], "WARNING", w["message"], w.get("entities", []), fix=w.get("fix"))
            for w in problem.warnings]


def errors(diags: list[Diagnostic]) -> list[Diagnostic]:
    return [d for d in diags if d.severity == "ERROR"]
