"""Background timetable generation.

Runs the engine off the request thread with a bounded worker pool (DoS guard), per-run cancel
flags and an in-memory progress stream for Server-Sent Events. CP-SAT releases the GIL while
solving, so threads are sufficient here; the ``submit`` interface is the seam for moving to an
external queue (Redis + arq) when solver workers need to scale separately from the API.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.core.errors import AppError, conflict
from app.models.identity import User
from app.models.timetable import GenerationRun, RunStatus, Timetable
from app.scheduling.engine import generate
from app.services import audit, notifications
from app.services.audit import RequestCtx
from app.services.timetables import ensure_editable, problem_for, save_outcome

log = logging.getLogger("app.generation")


@dataclass
class _RunState:
    cancel: threading.Event = field(default_factory=threading.Event)
    events: list[dict] = field(default_factory=list)
    done: bool = False
    cond: threading.Condition = field(default_factory=threading.Condition)

    def push(self, event: dict) -> None:
        with self.cond:
            self.events.append({**event, "t": round(time.time(), 2)})
            if len(self.events) > 500:
                del self.events[: len(self.events) - 500]
            self.cond.notify_all()


class GenerationService:
    def __init__(self) -> None:
        s = get_settings()
        self._pool = ThreadPoolExecutor(max_workers=s.max_concurrent_runs, thread_name_prefix="solver")
        self._runs: dict[str, _RunState] = {}
        self._lock = threading.Lock()

    def state(self, run_id: str) -> _RunState | None:
        return self._runs.get(run_id)

    def submit(self, db: Session, tt: Timetable, user: User, *, mode: str, time_limit_s: int, ctx: RequestCtx) -> GenerationRun:
        ensure_editable(tt)
        active = db.execute(select(GenerationRun).where(
            GenerationRun.timetable_id == tt.id,
            GenerationRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))).scalars().first()
        if active is not None:
            raise conflict("A generation is already running for this timetable.", run_id=active.id)
        with self._lock:
            running = sum(1 for st in self._runs.values() if not st.done)
        if running >= get_settings().max_concurrent_runs * 2:
            raise AppError(429, "busy", "The scheduler is busy. Please try again in a minute.")
        run = GenerationRun(timetable_id=tt.id, mode=mode, time_limit_s=time_limit_s, requested_by_id=user.id)
        db.add(run)
        db.flush()
        tt.last_run_id = run.id
        audit.record(db, action="timetable.generate", category="TIMETABLE", actor=user, entity="timetable",
                     entity_id=tt.id, ctx=ctx, summary=f"Started {mode} generation of '{tt.name}'",
                     data={"run_id": run.id, "mode": mode, "time_limit_s": time_limit_s})
        db.commit()
        st = _RunState()
        st.push({"event": "queued", "message": "Waiting for a free solver"})
        self._runs[run.id] = st
        self._pool.submit(self._execute, run.id, user.id, ctx)
        return run

    def cancel(self, run_id: str) -> bool:
        st = self._runs.get(run_id)
        if st is None or st.done:
            return False
        st.cancel.set()
        return True

    # ------------------------------------------------------------------ worker
    def _execute(self, run_id: str, user_id: str, ctx: RequestCtx) -> None:
        st = self._runs[run_id]
        db = SessionLocal()
        try:
            run = db.get(GenerationRun, run_id)
            tt = db.get(Timetable, run.timetable_id)
            user = db.get(User, user_id)
            run.status, run.started_at = RunStatus.RUNNING, utcnow()
            db.commit()
            st.push({"event": "phase", "phase": "build", "message": "Collecting inputs"})
            # Locked sessions are always respected. "unlocked" mode additionally keeps the remaining
            # sessions close to where they were (stability); "full" starts fresh.
            problem = problem_for(db, tt, keep_locked=True)
            if run.mode == "full":
                problem.previous = {}
            st.push({"event": "phase", "phase": "build", "message": f"{len(problem.units)} sessions to schedule",
                     "total": len(problem.units)})
            outcome = generate(problem, time_limit_s=run.time_limit_s, workers=get_settings().solver_workers,
                               on_progress=st.push, cancel=st.cancel)

            if outcome.placements or outcome.status in ("SUCCESS", "INFEASIBLE"):
                save_outcome(db, tt, problem, outcome)
            run.status = RunStatus(outcome.status)
            run.finished_at = utcnow()
            run.stats = {**outcome.stats, "quality": outcome.quality,
                         "scheduled": len(outcome.placements), "total": len(problem.units),
                         "locked": sum(1 for p in problem.pins.values() if p.reason == "locked")}
            run.diagnostics = outcome.diagnostics
            run.unassigned = outcome.unassigned
            audit.record(db, action="timetable.generated", category="TIMETABLE", actor=user, entity="timetable",
                         entity_id=tt.id, ctx=ctx, outcome="SUCCESS" if outcome.status == "SUCCESS" else "FAILURE",
                         summary=f"Generation of '{tt.name}' " + {
                             "SUCCESS": "finished successfully", "INFEASIBLE": "could not place every session",
                             "PRECHECK_FAILED": "stopped: inputs need attention", "TIMEOUT": "reached its time limit",
                             "CANCELLED": "was cancelled"}.get(outcome.status, "failed"),
                         data={"run_id": run_id, "scheduled": len(outcome.placements), "total": len(problem.units)})
            title = {"SUCCESS": "Timetable generated successfully", "INFEASIBLE": "Timetable could not be completed",
                     "PRECHECK_FAILED": "Timetable inputs need attention"}.get(outcome.status, f"Generation {outcome.status.lower()}")
            notifications.notify(db, [user], kind="generation", title=title,
                                 body=f"{tt.name}: {len(outcome.placements)}/{len(problem.units)} sessions scheduled.",
                                 link=f"/generate/report/{run_id}")
            db.commit()
            st.push({"event": "done", "status": outcome.status, "scheduled": len(outcome.placements),
                     "total": len(problem.units)})
        except Exception:  # noqa: BLE001 - recorded as FAILED, never as success
            log.exception("Generation run %s failed", run_id)
            db.rollback()
            run = db.get(GenerationRun, run_id)
            if run is not None:
                run.status, run.finished_at = RunStatus.FAILED, utcnow()
                run.diagnostics = [{"code": "FAILED", "severity": "ERROR",
                                    "message": "Generation failed unexpectedly. The error has been logged."}]
                db.commit()
            st.push({"event": "done", "status": "FAILED"})
        finally:
            st.done = True
            with st.cond:
                st.cond.notify_all()
            db.close()


generation_service = GenerationService()
