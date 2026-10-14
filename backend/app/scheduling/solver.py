"""CP-SAT timetable model.

Decision variables x[u, d, p, r] exist only for feasible combinations (faculty available for every
covered period, contiguous, suitable room free), so most hard rules are enforced by domain
filtering. The rest are linear constraints:

* every unit scheduled exactly once                (H-7)   — or at most once in *relaxed* mode
* at most one unit per (room | faculty | atom, slot) (H-3, H-4)
* faculty / group daily limits, faculty weekly limit
* pinned (fixed or locked) units restricted to their slot (H-8)

Preferences form a weighted penalty objective (spread, preferred slots, late periods, stability).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.scheduling.domain import Placement, Problem, SessionUnit

ProgressFn = Callable[[dict], None]


@dataclass
class SolveResult:
    status: str  # SUCCESS | INFEASIBLE | TIMEOUT | CANCELLED | FAILED
    placements: dict[str, Placement] = field(default_factory=dict)
    unassigned: list[str] = field(default_factory=list)
    objective: float | None = None
    stats: dict = field(default_factory=dict)
    core: list[str] = field(default_factory=list)  # unit keys in an infeasible subset (if computed)


class _Progress(cp_model.CpSolverSolutionCallback):
    def __init__(self, on_progress: ProgressFn | None, cancel: threading.Event | None, n_units: int, assigned_expr):
        super().__init__()
        self._on = on_progress
        self._cancel = cancel
        self._t0 = time.perf_counter()
        self._n = n_units
        self._assigned = assigned_expr
        self.solutions = 0

    def on_solution_callback(self) -> None:
        self.solutions += 1
        if self._on:
            placed = self._n if self._assigned is None else int(self.Value(self._assigned))
            self._on({"event": "solution", "solutions": self.solutions, "objective": self.ObjectiveValue(),
                      "bound": self.BestObjectiveBound(), "placed": placed, "total": self._n,
                      "elapsed_s": round(time.perf_counter() - self._t0, 2)})
        if self._cancel is not None and self._cancel.is_set():
            self.StopSearch()


class TimetableModel:
    def __init__(self, problem: Problem, *, relaxed: bool = False, with_assumptions: bool = False):
        self.p = problem
        self.relaxed = relaxed
        self.m = cp_model.CpModel()
        self.x: dict[tuple[str, int, int, str], cp_model.IntVar] = {}
        self.by_unit: dict[str, list[tuple[tuple[int, int, str], cp_model.IntVar]]] = defaultdict(list)
        self.assigned: dict[str, cp_model.IntVar] = {}
        self.assumption: dict[str, cp_model.IntVar] = {}
        self._build(with_assumptions)

    # ------------------------------------------------------------------ build
    def _candidates(self, u: SessionUnit):
        p = self.p
        pin = p.pins.get(u.key)
        starts = p.starts_for(u)
        if pin:
            starts = [(pin.day, pin.period)] if p.grid.contiguous(pin.day, pin.period, u.length) else []
        rooms = p.rooms_for(u)
        if pin and pin.room_id:
            rooms = [p.rooms[pin.room_id]] if pin.room_id in p.rooms else []
        for d, s in starts:
            for r in rooms:
                if p.room_free(r, d, s, u.length):
                    yield d, s, r.id

    def _build(self, with_assumptions: bool) -> None:
        p, m = self.p, self.m
        occ: dict[tuple[str, str, int, int], list] = defaultdict(list)
        starts_by: dict[tuple[str, str, int], list[tuple[int, cp_model.IntVar]]] = defaultdict(list)  # (rtype,id,day)

        for u in p.units:
            for d, s, rid in self._candidates(u):
                v = m.NewBoolVar(f"x|{u.key}|{d}|{s}|{rid}")
                self.x[(u.key, d, s, rid)] = v
                self.by_unit[u.key].append(((d, s, rid), v))
                for q in range(s, s + u.length):
                    occ[("room", rid, d, q)].append(v)
                    for f in u.faculty_ids:
                        occ[("faculty", f, d, q)].append(v)
                    for a in u.atoms:
                        occ[("atom", a, d, q)].append(v)
                for f in u.faculty_ids:
                    starts_by[("faculty", f, d)].append((u.length, v))
                for a in u.atoms:
                    starts_by[("atom", a, d)].append((u.length, v))

            vars_u = [v for _, v in self.by_unit[u.key]]
            if self.relaxed:
                a = m.NewBoolVar(f"a|{u.key}")
                self.assigned[u.key] = a
                m.Add(a == 0) if not vars_u else m.Add(sum(vars_u) == a)
            elif with_assumptions:
                lit = m.NewBoolVar(f"must|{u.key}")
                self.assumption[u.key] = lit
                if not vars_u:
                    m.Add(lit == 0)  # this unit alone is unschedulable -> it appears in the core
                else:
                    m.AddAtMostOne(vars_u)
                    m.AddBoolOr(vars_u).OnlyEnforceIf(lit)
            elif not vars_u:
                m.Add(m.NewConstant(0) == 1)  # no candidate slot at all: strict model is infeasible
            else:
                m.AddExactlyOne(vars_u)

        for vs in occ.values():
            if len(vs) > 1:
                m.AddAtMostOne(vs)
        self._occ = occ

        # Daily limits
        for (rtype, rid, _day), items in starts_by.items():
            lim = p.faculty_daily_limit(rid) if rtype == "faculty" else None
            if rtype == "atom":
                gid = self._group_of_atom(rid)
                lim = p.group_daily_limit(gid) if gid else None
            if lim and sum(L for L, _ in items) > lim:
                m.Add(sum(L * v for L, v in items) <= lim)
        for f in p.faculty.values():
            if f.max_per_week:
                items = [(L, v) for (rt, rid, _), its in starts_by.items() if rt == "faculty" and rid == f.id for L, v in its]
                if sum(L for L, _ in items) > f.max_per_week:
                    m.Add(sum(L * v for L, v in items) <= f.max_per_week)

        self._spread_and_objective()

    def _group_of_atom(self, atom: str) -> str | None:
        for g in self.p.groups.values():
            if atom in g.atoms:
                return g.id
        return None

    def _spread_and_objective(self) -> None:
        p, m, o = self.p, self.m, self.p.options
        penalty = []

        # Spread theory periods of a subject across days (per class)
        if o.spread_mode != "OFF":
            fam_day: dict[tuple, list] = defaultdict(list)
            for u in p.units:
                if u.kind != "THEORY":
                    continue
                for (d, _, _), v in self.by_unit[u.key]:
                    fam_day[(u.family, d)].append(v)
            for (_, _), vs in fam_day.items():
                if len(vs) <= 1:
                    continue
                if o.spread_mode == "HARD":
                    m.Add(sum(vs) <= 1)
                else:
                    excess = m.NewIntVar(0, len(vs), "spread_excess")
                    m.Add(excess >= sum(vs) - 1)
                    penalty.append(o.spread_weight * 10 * excess)

        for u in p.units:
            prev = p.previous.get(u.key)
            for (d, s, rid), v in self.by_unit[u.key]:
                cost = 0
                cov = p.grid.covered(d, s, u.length)
                for fid in u.faculty_ids:
                    f = p.faculty.get(fid)
                    if f and f.preferred and not all(c in f.preferred for c in cov):
                        cost += o.preferred_weight * 3
                if s + u.length == p.grid.n_periods(d):
                    cost += o.late_weight
                win = p.rules.subject_windows.get(u.subject_id)
                if win and not win.hard and not all(c in win.allowed for c in cov):
                    cost += win.weight * 3
                home = p.groups[u.group_id].home_room if u.group_id in p.groups else None
                if u.kind == "THEORY" and home and rid != home:
                    cost += o.home_room_weight
                if prev is not None:
                    if (prev.day, prev.period) != (d, s):
                        cost += o.stability_weight * 4
                    elif prev.room_id != rid:
                        cost += o.stability_weight
                if cost:
                    penalty.append(cost * v)
                if prev is not None and (prev.day, prev.period, prev.room_id) == (d, s, rid):
                    m.AddHint(v, 1)

        # Custom rule: at most N consecutive teaching periods per faculty member
        grid = p.grid
        for f in p.faculty.values():
            rule = p.rules.consecutive_for(f.id)
            if not rule:
                continue
            n, hard, weight = rule
            for d in grid.days:
                for q in range(grid.n_periods(d) - n):
                    if not grid.contiguous(d, q, n + 1):
                        continue
                    vs = [v for k in range(q, q + n + 1) for v in self._occ.get(("faculty", f.id, d, k), [])]
                    if len(vs) <= n:
                        continue
                    if hard:
                        m.Add(sum(vs) <= n)
                    else:
                        over = m.NewBoolVar("consec_over")
                        m.Add(sum(vs) <= n + over)
                        penalty.append(weight * 6 * over)

        # Symmetry breaking for interchangeable units (strict mode only, no pins/previous)
        if not self.relaxed and not self.assumption:
            fams: dict[tuple, list[SessionUnit]] = defaultdict(list)
            for u in p.units:
                if u.key not in p.pins and u.key not in p.previous:
                    fams[u.family].append(u)
            width = max((p.grid.n_periods(d) for d in p.grid.days), default=1)
            for us in fams.values():
                if len(us) < 2:
                    continue
                us.sort(key=lambda u: u.index)
                idx = [sum((d * width + s) * v for (d, s, _), v in self.by_unit[u.key]) for u in us]
                for a, b in zip(idx, idx[1:], strict=False):
                    m.Add(a < b)

        if self.relaxed:
            big = 10_000
            self.m.Minimize(sum(penalty) - big * sum(self.assigned.values()))
        elif penalty:
            self.m.Minimize(sum(penalty))

    # ------------------------------------------------------------------ solve
    def solve(self, time_limit_s: float, workers: int, *, on_progress: ProgressFn | None = None,
              cancel: threading.Event | None = None, seed: int = 7) -> SolveResult:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit_s)
        solver.parameters.num_workers = 1 if self.assumption else max(1, workers)
        solver.parameters.random_seed = seed
        if self.assumption:
            self.m.AddAssumptions(list(self.assumption.values()))

        assigned_expr = None
        if self.relaxed and self.assigned:
            assigned_expr = sum(self.assigned.values())
        cb = _Progress(on_progress, cancel, len(self.p.units), assigned_expr)
        t0 = time.perf_counter()
        code = solver.Solve(self.m, cb)
        elapsed = round(time.perf_counter() - t0, 3)

        stats = {"solver_status": solver.StatusName(code), "wall_time_s": elapsed, "variables": len(self.x),
                 "units": len(self.p.units), "solutions": cb.solutions,
                 "conflicts": solver.NumConflicts(), "branches": solver.NumBranches()}
        cancelled = cancel is not None and cancel.is_set()

        if code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            placements: dict[str, Placement] = {}
            for (key, d, s, rid), v in self.x.items():
                if solver.BooleanValue(v):
                    placements[key] = Placement(key, d, s, rid)
            unassigned = [u.key for u in self.p.units if u.key not in placements]
            stats["optimal"] = code == cp_model.OPTIMAL
            stats["objective"] = solver.ObjectiveValue() if self.m.HasObjective() else 0
            if unassigned:
                status = "INFEASIBLE"
            else:
                status = "SUCCESS"
            return SolveResult(status, placements, unassigned, stats.get("objective"), stats)
        if code == cp_model.INFEASIBLE:
            core: list[str] = []
            if self.assumption:
                idx_to_key = {lit.Index(): k for k, lit in self.assumption.items()}
                core = [idx_to_key[i] for i in solver.SufficientAssumptionsForInfeasibility() if i in idx_to_key]
            return SolveResult("INFEASIBLE", unassigned=[u.key for u in self.p.units], stats=stats, core=core)
        if cancelled:
            return SolveResult("CANCELLED", stats=stats)
        if code == cp_model.UNKNOWN:
            return SolveResult("TIMEOUT", stats=stats)
        return SolveResult("FAILED", stats=stats)


def solve(problem: Problem, *, time_limit_s: float = 30, workers: int = 8, on_progress: ProgressFn | None = None,
          cancel: threading.Event | None = None) -> SolveResult:
    return TimetableModel(problem).solve(time_limit_s, workers, on_progress=on_progress, cancel=cancel)


def solve_relaxed(problem: Problem, *, time_limit_s: float = 15, workers: int = 8,
                  on_progress: ProgressFn | None = None, cancel: threading.Event | None = None) -> SolveResult:
    """Place as many sessions as possible. Used to explain infeasibility, never for publishing."""
    return TimetableModel(problem, relaxed=True).solve(time_limit_s, workers, on_progress=on_progress, cancel=cancel)


def find_core(problem: Problem, *, time_limit_s: float = 10) -> list[str]:
    """Return a (small) set of units that cannot all be scheduled together."""
    res = TimetableModel(problem, with_assumptions=True).solve(time_limit_s, 1)
    return res.core
