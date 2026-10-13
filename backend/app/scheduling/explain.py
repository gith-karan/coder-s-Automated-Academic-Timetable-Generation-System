"""Layer-3 diagnostics: explain why the solver could not place some sessions.

* ``explain_core``     — names the resources shared by an infeasible subset of sessions.
* ``blocking_analysis`` — for every unplaced session, inspects each slot its faculty is free and
  reports what blocks it (faculty busy, class busy, no free suitable room) in the best partial plan.
"""
from __future__ import annotations

from collections import Counter

from app.scheduling.domain import Placement, Problem, build_occupancy
from app.scheduling.prechecks import Diagnostic


def explain_core(problem: Problem, core: list[str]) -> list[Diagnostic]:
    if not core:
        return []
    units = [problem.unit_by_key[k] for k in core if k in problem.unit_by_key]
    if not units:
        return []
    fac_count = Counter(f for u in units for f in u.faculty_ids)
    atom_count = Counter(a for u in units for a in u.atoms)
    lab_count = Counter(u.lab_type for u in units if u.room_kind == "LAB")
    shared: list[str] = []
    ents: list[dict] = []
    for fid, n in fac_count.most_common():
        if n >= 2:
            f = problem.faculty[fid]
            shared.append(f"{f.name}'s available periods")
            ents.append({"type": "faculty", "id": fid, "label": f.name})
    for g in problem.groups.values():
        if any(atom_count.get(a, 0) >= 2 for a in g.atoms):
            shared.append(f"{g.label}'s free periods")
            ents.append({"type": "group", "id": g.id, "label": g.label})
    for lt, n in lab_count.items():
        if n >= 2:
            shared.append(f"{lt or 'laboratory'} capacity")
    subjects = sorted({u.subject_code for u in units})
    if len(units) == 1:
        u = units[0]
        msg = f"{u.label} cannot be placed in any slot that satisfies all mandatory rules."
    else:
        competing = ", ".join(shared[:3]) if shared else "the same limited time slots"
        msg = (f"{len(units)} sessions ({', '.join(subjects[:6])}{'…' if len(subjects) > 6 else ''}) cannot all be "
               f"scheduled together: they compete for {competing}.")
    fix = {"page": "faculty", "id": ents[0]["id"], "tab": "availability"} if ents and ents[0]["type"] == "faculty" else None
    return [Diagnostic("CONFLICTING_REQUIREMENTS", "ERROR", msg, ents, list(core), fix)]


def blocking_analysis(problem: Problem, placements: dict[str, Placement], unassigned: list[str]) -> list[dict]:
    occ = build_occupancy(problem, placements)
    out: list[dict] = []
    for key in unassigned:
        u = problem.unit_by_key.get(key)
        if u is None:
            continue
        starts = problem.starts_for(u)
        rooms = problem.rooms_for(u)
        busy_fac: Counter = Counter()
        busy_grp: Counter = Counter()
        no_room = 0
        for d, s in starts:
            cov = problem.grid.covered(d, s, u.length)
            blocked = False
            for f in u.faculty_ids:
                hits = {k for c in cov for k in occ.get(("faculty", f, *c), [])}
                if hits:
                    busy_fac.update(problem.unit_by_key[k].subject_code for k in hits)
                    blocked = True
            for a in u.atoms:
                hits = {k for c in cov for k in occ.get(("atom", a, *c), [])}
                if hits:
                    busy_grp.update(problem.unit_by_key[k].subject_code for k in hits)
                    blocked = True
            if not blocked:
                free = [r for r in rooms if problem.room_free(r, d, s, u.length)
                        and not any(occ.get(("room", r.id, *c)) for c in cov)]
                if not free:
                    no_room += 1
        reasons: list[str] = []
        if not starts:
            reasons.append("its faculty has no suitable free time window")
        if busy_fac:
            reasons.append("faculty already teaching " + ", ".join(c for c, _ in busy_fac.most_common(4)))
        if busy_grp:
            reasons.append("students already in " + ", ".join(c for c, _ in busy_grp.most_common(4)))
        if no_room:
            reasons.append(f"no suitable room free in {no_room} candidate slot(s)")
        faculty_names = [problem.faculty[f].name for f in u.faculty_ids if f in problem.faculty]
        out.append({
            "key": key, "subject_id": u.subject_id, "subject_code": u.subject_code, "subject_name": u.subject_name,
            "audience": u.audience, "kind": u.kind, "length": u.length, "faculty": faculty_names,
            "candidate_slots": len(starts),
            "reason": ("Every slot was blocked: " + "; ".join(reasons)) if reasons else "Blocked by combined constraints",
        })
    return out
