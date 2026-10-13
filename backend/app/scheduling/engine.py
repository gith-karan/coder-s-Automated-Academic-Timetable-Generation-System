"""One entry point that runs the full pipeline:

pre-checks -> strict solve -> (if infeasible) core + best partial plan + blocking analysis
-> independent validation -> quality score.

The outcome is never "SUCCESS" unless every session is placed and the validator finds zero
mandatory-rule violations (PS §3).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from app.scheduling import prechecks
from app.scheduling.domain import Placement, Problem
from app.scheduling.explain import blocking_analysis, explain_core
from app.scheduling.scoring import score
from app.scheduling.solver import ProgressFn, find_core, solve, solve_relaxed
from app.scheduling.validator import hard, validate


@dataclass
class Outcome:
    status: str  # SUCCESS | INFEASIBLE | PRECHECK_FAILED | TIMEOUT | CANCELLED | FAILED
    placements: dict[str, Placement] = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)
    unassigned: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    quality: dict | None = None


def generate(problem: Problem, *, time_limit_s: float, workers: int, on_progress: ProgressFn | None = None,
             cancel: threading.Event | None = None) -> Outcome:
    emit = on_progress or (lambda _e: None)

    emit({"event": "phase", "phase": "precheck", "message": "Checking inputs"})
    diags = _dedupe(prechecks.run_prechecks(problem))
    errs = prechecks.errors(diags)
    stats: dict = {"units": len(problem.units), "periods_per_week": len(problem.grid.all_slots())}
    if errs:
        return Outcome("PRECHECK_FAILED", diagnostics=[d.to_dict() for d in diags], stats=stats,
                       unassigned=[{"key": k} for d in errs for k in d.sessions][:500])
    if not problem.units:
        return Outcome("PRECHECK_FAILED", stats=stats, diagnostics=[prechecks.Diagnostic(
            "NOTHING_TO_SCHEDULE", "ERROR", "There are no sessions to schedule. Add subjects with weekly periods.",
            fix={"page": "subjects"}).to_dict()])

    emit({"event": "phase", "phase": "solve", "message": "Building and solving the timetable model"})
    res = solve(problem, time_limit_s=time_limit_s, workers=workers, on_progress=on_progress, cancel=cancel)
    stats.update(res.stats)

    if res.status == "SUCCESS":
        violations = validate(problem, res.placements)
        if hard(violations):  # defence in depth: should never happen
            return Outcome("FAILED", res.placements, [{"code": "VALIDATION_FAILED", "severity": "ERROR",
                                                        "message": v.message} for v in hard(violations)], stats=stats)
        q = score(problem, res.placements)
        diags_out = [d.to_dict() for d in diags] + [
            {"code": v.code, "severity": "WARNING", "message": v.message, "sessions": v.keys} for v in violations]
        return Outcome("SUCCESS", res.placements, diags_out, [], stats, q)

    if res.status in ("TIMEOUT", "CANCELLED", "FAILED"):
        return Outcome(res.status, diagnostics=[d.to_dict() for d in diags] + [{
            "code": res.status, "severity": "ERROR",
            "message": {"TIMEOUT": f"No complete timetable was found within {int(time_limit_s)} seconds. "
                                   "Increase the time limit or relax some constraints.",
                        "CANCELLED": "Generation was cancelled.",
                        "FAILED": "The solver failed unexpectedly."}[res.status]}], stats=stats)

    # INFEASIBLE: explain it.
    emit({"event": "phase", "phase": "diagnose", "message": "No complete timetable exists — finding the cause"})
    core = find_core(problem, time_limit_s=max(5.0, time_limit_s / 3))
    core_diags = explain_core(problem, core)
    partial = solve_relaxed(problem, time_limit_s=max(5.0, time_limit_s / 2), workers=workers, cancel=cancel)
    blocking = blocking_analysis(problem, partial.placements, partial.unassigned)
    stats["placed"] = len(partial.placements)
    stats["core_size"] = len(core)
    q = score(problem, partial.placements) if partial.placements else None
    diag_out = [d.to_dict() for d in diags] + [d.to_dict() for d in core_diags]
    if not core_diags:
        diag_out.append({"code": "INFEASIBLE", "severity": "ERROR", "entities": [], "sessions": partial.unassigned,
                         "message": f"No timetable satisfies every mandatory rule. {len(partial.unassigned)} session(s) "
                                    "could not be placed; see Unassigned Sessions for the reasons."})
    return Outcome("INFEASIBLE", partial.placements, diag_out, blocking, stats, q)


def _dedupe(diags: list[prechecks.Diagnostic]) -> list[prechecks.Diagnostic]:
    seen: set[tuple[str, str]] = set()
    out = []
    for d in diags:
        if (d.code, d.message) not in seen:
            seen.add((d.code, d.message))
            out.append(d)
    return out
