"""Calendar, constraints, system settings, readiness pre-flight, availability requests, dashboard."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, require_perm, require_roles
from app.core.db import get_db
from app.core.errors import bad_request
from app.core.roles import EVERYONE, Role
from app.models.academic import (
    Break, ConstraintSetting, Faculty, Programme, Room, RoomKind, StudentGroup, Subject,
)
from app.models.audit import AuditLog
from app.models.identity import User
from app.models.timetable import GenerationRun, Timetable, TimetableStatus
from app.models.workflow import ChangeRequest, RequestStatus
from app.scheduling import prechecks
from app.scheduling.timegrid import BreakSpec, TimeGrid, to_minutes
from app.schemas.academic import AvailabilityIn, CalendarIn, ConstraintIn
from app.schemas.common import ShortText, StrictModel
from app.services import audit, constraints, system_settings, workflow
from app.services.problem_builder import build_problem, faculty_slots, load_calendar, load_grid

router = APIRouter()
_edit = require_perm("setup.edit")
_view = require_perm("setup.view")
_any = require_roles(*EVERYONE)


# ------------------------------------------------------------------ calendar
def _calendar_dict(db: Session) -> dict:
    cal = load_calendar(db)
    breaks = db.execute(select(Break).order_by(Break.start_time)).scalars().all()
    return {"working_days": cal.working_days, "day_start": cal.day_start, "day_end": cal.day_end,
            "period_minutes": cal.period_minutes,
            "breaks": [{"name": b.name, "start_time": b.start_time, "end_time": b.end_time, "days": b.days}
                       for b in breaks],
            "grid": load_grid(db).to_dict()}


@router.get("/calendar", tags=["calendar"])
def get_calendar(p: Principal = Depends(_any), db: Session = Depends(get_db)):
    return _calendar_dict(db)


@router.post("/calendar/preview", tags=["calendar"])
def preview_calendar(body: CalendarIn, p: Principal = Depends(_view)):
    """Live preview of the period grid while the coordinator edits (nothing is saved)."""
    grid = TimeGrid(body.working_days, to_minutes(body.day_start), to_minutes(body.day_end), body.period_minutes,
                    [BreakSpec(b.name, to_minutes(b.start_time), to_minutes(b.end_time),
                               frozenset(b.days) if b.days else None) for b in body.breaks])
    return grid.to_dict()


@router.put("/calendar", tags=["calendar"])
def put_calendar(body: CalendarIn, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    before = _calendar_dict(db)
    before.pop("grid")
    cal = load_calendar(db)
    for k in ("working_days", "day_start", "day_end", "period_minutes"):
        setattr(cal, k, getattr(body, k))
    db.execute(delete(Break))
    for b in body.breaks:
        db.add(Break(name=b.name, start_time=b.start_time, end_time=b.end_time, days=b.days))
    db.flush()
    if not load_grid(db).all_slots():
        raise bad_request("These settings produce no teaching periods. Check hours, period length and breaks.")
    audit.record(db, action="calendar.update", category="DATA", actor=p.user, entity="calendar", entity_id="1",
                 ctx=p.ctx, summary="Updated university timings", data={"before": before,
                                                                        "after": body.model_dump()})
    db.commit()
    return _calendar_dict(db)


# ------------------------------------------------------------------ constraints
@router.get("/constraints", tags=["constraints"])
def get_constraints(p: Principal = Depends(_view), db: Session = Depends(get_db)):
    return {"mandatory": constraints.MANDATORY_RULES, "configurable": constraints.current(db)}


class ConstraintsIn(StrictModel):
    items: Annotated[list[ConstraintIn], Field(max_length=50)]


@router.put("/constraints", tags=["constraints"])
def put_constraints(body: ConstraintsIn, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    changes = []
    for item in body.items:
        err = constraints.validate_setting(item.key, item.mode)
        if err:
            raise bad_request(err)
        row = db.get(ConstraintSetting, item.key)
        if row is None:
            row = ConstraintSetting(key=item.key, mode=item.mode, weight=item.weight, value=item.value)
            db.add(row)
        else:
            row.mode, row.weight, row.value = item.mode, item.weight, item.value
        changes.append(item.model_dump(mode="json"))
    audit.record(db, action="constraints.update", category="DATA", actor=p.user, entity="constraints", ctx=p.ctx,
                 summary=f"Updated {len(changes)} scheduling constraint(s)", data={"changes": changes})
    db.commit()
    return {"mandatory": constraints.MANDATORY_RULES, "configurable": constraints.current(db)}


# ------------------------------------------------------------------ system settings (admin)
@router.get("/system-settings", tags=["settings"])
def get_system_settings(p: Principal = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return {"solver_time_limit_s": system_settings.get(db, "solver_time_limit_s")}


class SystemSettingsIn(StrictModel):
    solver_time_limit_s: Annotated[int, Field(ge=10, le=300)] | None = None


@router.put("/system-settings", tags=["settings"])
def put_system_settings(body: SystemSettingsIn, p: Principal = Depends(require_roles(Role.ADMIN)),
                        db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    before = system_settings.all_settings(db)
    for k, v in data.items():
        system_settings.set_value(db, k, v)
    audit.record(db, action="settings.update", category="SECURITY", actor=p.user, entity="system_settings", ctx=p.ctx,
                 summary="Changed system settings", data={"before": before, "after": data})
    db.commit()
    return {"solver_time_limit_s": system_settings.get(db, "solver_time_limit_s")}


# ------------------------------------------------------------------ faculty availability (maker–checker)
class AvailabilityRequestIn(StrictModel):
    availability: AvailabilityIn
    reason: ShortText = ""


@router.put("/faculty/{faculty_id}/availability", tags=["faculty"])
def set_availability(faculty_id: str, body: AvailabilityRequestIn, p: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)):
    res = workflow.request_availability(db, p, faculty_id, body.availability.model_dump(mode="json"), body.reason)
    return {"applied": res["applied"], "request_id": res["request"].id if res["request"] else None}


@router.get("/me/faculty-profile", tags=["faculty"])
def my_faculty_profile(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """A faculty member's own profile (works without 'setup.view')."""
    from app.schemas.academic import FacultyOut

    fac = db.get(Faculty, p.user.faculty_id) if p.user.faculty_id else None
    if fac is None:
        raise bad_request("Your account is not linked to a faculty profile.")
    return FacultyOut.model_validate(fac)


@router.get("/faculty/{faculty_id}/availability-summary", tags=["faculty"])
def availability_summary(faculty_id: str, p: Principal = Depends(_view),
                         db: Session = Depends(get_db)):
    fac = db.get(Faculty, faculty_id)
    if fac is None:
        raise bad_request("Faculty not found.")
    grid = load_grid(db)
    avail, pref = faculty_slots(grid, fac)
    load = sum((s.periods_per_week or s.sessions_per_week * s.consecutive_periods) for s in fac.subjects)
    return {"available_periods": len(avail), "preferred_periods": len(pref), "assigned_periods_estimate": load,
            "available": sorted(avail), "preferred": sorted(pref)}


# ------------------------------------------------------------------ readiness pre-flight
@router.get("/readiness", tags=["generate"])
def readiness(programme_ids: list[str] = Query(default=[]), semesters: list[int] = Query(default=[]),
              term: str | None = Query(None, pattern="^(ODD|EVEN)$"),
              p: Principal = Depends(require_perm("timetable.generate")), db: Session = Depends(get_db)):
    problem = build_problem(db, programme_ids=programme_ids or None, semesters=semesters or None, term=term)
    diags = prechecks.run_prechecks(problem)
    counts = {
        "calendar": len(problem.grid.all_slots()) > 0,
        "rooms": db.execute(select(func.count()).select_from(Room).where(Room.is_active.is_(True))).scalar_one(),
        "programmes": db.execute(select(func.count()).select_from(Programme)).scalar_one(),
        "classes": len(problem.groups),
        "faculty": db.execute(select(func.count()).select_from(Faculty)).scalar_one(),
        "subjects": db.execute(select(func.count()).select_from(Subject)).scalar_one(),
        "sessions": len(problem.units),
        "periods_per_week": len(problem.grid.all_slots()),
    }
    seen: set[tuple[str, str]] = set()
    unique = [d for d in diags if not ((d.code, d.message) in seen or seen.add((d.code, d.message)))]
    return {"ready": not prechecks.errors(unique) and counts["sessions"] > 0, "counts": counts,
            "diagnostics": [d.to_dict() for d in unique]}


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard", tags=["dashboard"])
def dashboard(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.timetables import timetable_summary

    def count(model, *where):
        return db.execute(select(func.count()).select_from(model).where(*where)).scalar_one()

    out: dict[str, Any] = {
        "counts": {"programmes": count(Programme), "subjects": count(Subject), "faculty": count(Faculty),
                   "rooms": count(Room, Room.is_active.is_(True)),
                   "labs": count(Room, Room.kind == RoomKind.LAB, Room.is_active.is_(True)),
                   "classes": count(StudentGroup)},
    }
    published = db.execute(select(Timetable).where(Timetable.status == TimetableStatus.PUBLISHED)
                           .order_by(Timetable.published_at.desc())).scalars().all()
    out["published"] = ({"id": published[0].id, "name": published[0].name,
                         "published_at": published[0].published_at.isoformat()} if published else None)
    # Timetable cards: every live (published) timetable, plus the most recent drafts for people who may see them.
    cards = [timetable_summary(t) for t in published]
    if p.can("timetable.view_drafts"):
        drafts = db.execute(select(Timetable).where(Timetable.status.in_([TimetableStatus.DRAFT, TimetableStatus.IN_REVIEW]))
                            .order_by(Timetable.updated_at.desc()).limit(20)).scalars().all()
        cards += [timetable_summary(t) for t in drafts]
    slots = len(load_grid(db).all_slots())
    rooms = max(count(Room, Room.is_active.is_(True)), 1)
    for c in cards:
        t = db.get(Timetable, c["id"])
        used = sum(e.length for e in t.entries if e.day is not None)
        c["room_use_pct"] = round(100 * used / max(slots * rooms, 1), 1)
    out["timetables"] = cards
    if p.can("requests.review") or p.can("timetable.publish"):
        out["pending_requests"] = count(ChangeRequest, ChangeRequest.status == RequestStatus.PENDING)
    if p.can("timetable.generate"):
        last_run = db.execute(select(GenerationRun).order_by(GenerationRun.created_at.desc())).scalars().first()
        out["last_run"] = {"id": last_run.id, "status": last_run.status.value,
                           "created_at": last_run.created_at.isoformat()} if last_run else None
    if p.can("setup.view"):
        acts = db.execute(select(AuditLog).where(AuditLog.category.in_(["DATA", "TIMETABLE", "USER", "WORKFLOW", "SYSTEM"]),
                                                 AuditLog.outcome == "SUCCESS")
                          .order_by(AuditLog.seq.desc()).limit(8)).scalars().all()
        out["recent_activity"] = [{"action": a.action, "summary": a.summary, "at": a.at.isoformat(),
                                   "actor": a.actor_email, "category": a.category} for a in acts]
    if p.can("users.view"):
        out["users"] = {r.value: count(User, User.role == r, User.is_active.is_(True)) for r in Role}
    return out
