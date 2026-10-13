"""Quality score (0–100) of a timetable based on soft preferences, with a per-preference breakdown.

Computed from placements (not from the solver), so it also scores manually-edited drafts.
"""
from __future__ import annotations

from collections import defaultdict

from app.scheduling.domain import Placement, Problem


def score(problem: Problem, placements: dict[str, Placement]) -> dict:
    units = problem.unit_by_key
    o = problem.options

    # Spread: theory periods of a subject on distinct days
    fam_days: dict[tuple, list[int]] = defaultdict(list)
    for k, pl in placements.items():
        u = units.get(k)
        if u and u.kind == "THEORY":
            fam_days[u.family].append(pl.day)
    spread_total = sum(len(ds) - 1 for ds in fam_days.values() if len(ds) > 1)
    spread_bad = sum(len(ds) - len(set(ds)) for ds in fam_days.values())

    # Preferred slots
    pref_total = pref_bad = 0
    for k, pl in placements.items():
        u = units.get(k)
        if not u:
            continue
        cov = problem.grid.covered(pl.day, pl.period, u.length)
        for fid in u.faculty_ids:
            f = problem.faculty.get(fid)
            if f and f.preferred:
                pref_total += 1
                if not all(c in f.preferred for c in cov):
                    pref_bad += 1

    # Student idle gaps (compactness), measured per atom and day
    atom_day: dict[tuple[str, int], set[int]] = defaultdict(set)
    for k, pl in placements.items():
        u = units.get(k)
        if not u:
            continue
        for a in u.atoms:
            atom_day[(a, pl.day)].update(range(pl.period, pl.period + u.length))
    gaps = sum((max(ps) - min(ps) + 1 - len(ps)) for ps in atom_day.values() if ps)
    gap_total = sum(len(ps) for ps in atom_day.values())

    def pct(bad: int, total: int) -> float:
        return 100.0 if total == 0 else round(100 * (1 - bad / total), 1)

    parts = {
        "spread": {"label": "Subjects spread across the week", "score": pct(spread_bad, max(spread_total, 1)) if spread_total else 100.0,
                   "weight": o.spread_weight if o.spread_mode == "SOFT" else 0},
        "preferred": {"label": "Faculty preferred slots honoured", "score": pct(pref_bad, pref_total),
                      "weight": o.preferred_weight},
        "compact": {"label": "Few idle gaps for students", "score": pct(gaps, gap_total), "weight": 2},
    }
    wsum = sum(p["weight"] for p in parts.values()) or 1
    overall = round(sum(p["score"] * p["weight"] for p in parts.values()) / wsum, 1)
    completeness = round(100 * len([k for k in placements if k in units]) / max(len(problem.units), 1), 1)
    return {"quality": overall, "completeness": completeness, "breakdown": parts}
