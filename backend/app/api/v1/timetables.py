from __future__ import annotations

import json
import time
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, deny, require_perm
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError, conflict, not_found
from app.exports import render
from app.models.academic import Faculty, Room, StudentGroup
from app.models.timetable import GenerationRun, Timetable, TimetableStatus
from app.models.workflow import RequestStatus
from app.schemas.common import Day, ShortText, StrictModel
from app.services import audit, system_settings, workflow
from app.services import timetables as svc
from app.services.generation import generation_service

router = APIRouter(prefix="/timetables", tags=["timetables"])
runs = APIRouter(prefix="/runs", tags=["generate"])
requests_router = APIRouter(prefix="/requests", tags=["requests"])

_any = current_principal
_drafts = require_perm("timetable.view_drafts")
_edit = require_perm("timetable.edit")


class TimetableIn(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    academic_year: Annotated[str, Field(pattern=r"^20\d{2}-\d{2}$")] | None = None
    term: Literal["ODD", "EVEN"] | None = None
    programme_ids: list[str] = Field(default_factory=list, max_length=50)
    semesters: list[Annotated[int, Field(ge=1, le=12)]] = Field(default_factory=list, max_length=12)


class GenerateIn(StrictModel):
    mode: Literal["full", "unlocked"] = "full"
    time_limit_s: Annotated[int, Field(ge=5, le=120)] | None = None


class MoveIn(StrictModel):
    day: Day
    start_period: Annotated[int, Field(ge=0, le=30)]
    room_id: str | None = None
    expected_version: int | None = None


class LockIn(StrictModel):
    entry_ids: Annotated[list[str], Field(min_length=1, max_length=2000)]
    locked: bool


class SubmitIn(StrictModel):
    note: ShortText = ""


class ReviewIn(StrictModel):
    approve: bool
    comment: ShortText = ""


class MoveRequestIn(StrictModel):
    entry_id: str
    day: Day
    start_period: Annotated[int, Field(ge=0, le=30)]
    reason: ShortText = ""


def _visible(p: Principal, tt: Timetable) -> Timetable:
    """Drafts (and timetables in review) need 'timetable.view_drafts'; published ones 'timetable.view_published'."""
    if p.can("timetable.view_drafts") or (p.can("timetable.view_published") and tt.status == TimetableStatus.PUBLISHED):
        return tt
    raise not_found("Timetable")


def _check_scope(p: Principal, by: str | None, ref: str | None) -> None:
    """Least privilege inside a timetable: own class / own teaching unless wider views are granted."""
    if p.can("timetable.view_drafts"):
        return
    if not by or not ref:
        if p.can("timetable.view_all_classes"):
            return
    elif by in ("group", "programme"):
        if p.can("timetable.view_all_classes") or (by == "group" and ref == p.user.group_id):
            return
    elif by == "faculty":
        if p.can("timetable.view_faculty") or ref == p.user.faculty_id:
            return
    elif by == "room" and p.can("timetable.view_rooms"):
        return
    raise deny(p, f"{p.role} tried to view a timetable outside their scope (by={by}, ref={ref})")


# ------------------------------------------------------------------ timetables
@router.get("")
def list_timetables(status: TimetableStatus | None = None, p: Principal = Depends(_any), db: Session = Depends(get_db)):
    stmt = select(Timetable).order_by(Timetable.updated_at.desc()).limit(200)
    if not p.can("timetable.view_drafts"):
        if not p.can("timetable.view_published"):
            return []
        stmt = stmt.where(Timetable.status == TimetableStatus.PUBLISHED)
    if status:
        stmt = stmt.where(Timetable.status == status)
    return [svc.timetable_summary(t) for t in db.execute(stmt).scalars()]


@router.post("", status_code=201)
def create_timetable(body: TimetableIn, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    if svc.name_taken(db, body.name):
        raise AppError(409, "duplicate_name", f"A timetable named '{body.name}' already exists.",
                       extra={"suggestion": svc.unique_name(db, body.name)})
    tt = Timetable(name=body.name, programme_ids=body.programme_ids, semesters=body.semesters, created_by_id=p.user.id,
                   academic_year=body.academic_year, term=body.term)
    db.add(tt)
    db.flush()
    audit.record(db, action="timetable.create", category="TIMETABLE", actor=p.user, entity="timetable",
                 entity_id=tt.id, ctx=p.ctx, summary=f"Created timetable draft '{tt.name}'", data=body.model_dump())
    db.commit()
    return svc.timetable_summary(tt)


@router.get("/{tid}")
def get_timetable(tid: str, by: Literal["group", "programme", "faculty", "room"] | None = None,
                  ref: str | None = None, p: Principal = Depends(_any), db: Session = Depends(get_db)):
    tt = _visible(p, svc.get_timetable(db, tid))
    _check_scope(p, by, ref)
    return svc.view(db, tt, by=by, ref=ref)


@router.get("/{tid}/directory")
def directory(tid: str, p: Principal = Depends(_any), db: Session = Depends(get_db)):
    """Classes, faculty and rooms that appear in this timetable — the options for the three views."""
    tt = _visible(p, svc.get_timetable(db, tid))
    d = svc.directory(db, tt)
    if not p.can("timetable.view_drafts"):  # only the options this user may actually open
        if not p.can("timetable.view_all_classes"):
            d["group"] = [g for g in d["group"] if g["id"] == p.user.group_id]
        if not p.can("timetable.view_faculty"):
            d["faculty"] = [f for f in d["faculty"] if f["id"] == p.user.faculty_id]
        if not p.can("timetable.view_rooms"):
            d["room"] = []
    return d


@router.delete("/{tid}", status_code=204)
def delete_timetable(tid: str, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    tt = svc.get_timetable(db, tid)
    if tt.status != TimetableStatus.DRAFT:
        raise conflict("Only drafts can be deleted. Published timetables are kept for the record.")
    audit.record(db, action="timetable.delete", category="TIMETABLE", actor=p.user, entity="timetable",
                 entity_id=tt.id, ctx=p.ctx, summary=f"Deleted draft '{tt.name}'")
    db.delete(tt)
    db.commit()
    return Response(status_code=204)


@router.post("/{tid}/duplicate", status_code=201)
def duplicate_timetable(tid: str, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    src = svc.get_timetable(db, tid)
    copy = workflow.duplicate(db, src, p.user)
    audit.record(db, action="timetable.duplicate", category="TIMETABLE", actor=p.user, entity="timetable",
                 entity_id=copy.id, ctx=p.ctx, summary=f"Duplicated '{src.name}' into a new draft")
    db.commit()
    return svc.timetable_summary(copy)


@router.get("/{tid}/validate")
def validate_timetable(tid: str, p: Principal = Depends(_drafts), db: Session = Depends(get_db)):
    return svc.validate_timetable(db, svc.get_timetable(db, tid))


@router.get("/{a}/diff/{b}")
def diff(a: str, b: str, p: Principal = Depends(_drafts), db: Session = Depends(get_db)):
    return svc.diff(svc.get_timetable(db, a), svc.get_timetable(db, b))


# ------------------------------------------------------------------ generation
@router.post("/{tid}/generate", status_code=202)
def generate(tid: str, body: GenerateIn, p: Principal = Depends(require_perm("timetable.generate")),
             db: Session = Depends(get_db)):
    tt = svc.get_timetable(db, tid)
    # The solver stops on its own once the best timetable is proven; this is only a safety cap.
    cap = int(system_settings.get(db, "solver_time_limit_s"))
    limit = min(int(body.time_limit_s or cap), cap, get_settings().solver_max_time_limit_s)
    run = generation_service.submit(db, tt, p.user, mode=body.mode, time_limit_s=limit, ctx=p.ctx)
    return {"run_id": run.id, "status": run.status.value}


def _run_dict(run: GenerationRun) -> dict:
    return {"id": run.id, "timetable_id": run.timetable_id, "status": run.status.value, "mode": run.mode,
            "time_limit_s": run.time_limit_s, "stats": run.stats, "diagnostics": run.diagnostics,
            "unassigned": run.unassigned, "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None}


@runs.get("")
def list_runs(timetable_id: str | None = None, p: Principal = Depends(_drafts), db: Session = Depends(get_db)):
    stmt = select(GenerationRun).order_by(GenerationRun.created_at.desc()).limit(50)
    if timetable_id:
        stmt = stmt.where(GenerationRun.timetable_id == timetable_id)
    return [_run_dict(r) for r in db.execute(stmt).scalars()]


@runs.get("/{run_id}")
def get_run(run_id: str, p: Principal = Depends(_drafts), db: Session = Depends(get_db)):
    run = db.get(GenerationRun, run_id)
    if run is None:
        raise not_found("Run")
    return _run_dict(run)


@runs.post("/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str, p: Principal = Depends(require_perm("timetable.generate")), db: Session = Depends(get_db)):
    if not generation_service.cancel(run_id):
        raise conflict("This run is not active.")
    audit.record(db, action="timetable.generate_cancel", category="TIMETABLE", actor=p.user, entity="run",
                 entity_id=run_id, ctx=p.ctx, summary="Cancelled a generation run")
    db.commit()
    return {"detail": "Cancelling"}


@runs.get("/{run_id}/events")
def run_events(run_id: str, p: Principal = Depends(_drafts), db: Session = Depends(get_db)):
    """Server-Sent Events stream of solver progress."""
    run = db.get(GenerationRun, run_id)
    if run is None:
        raise not_found("Run")
    st = generation_service.state(run_id)

    def stream():
        yield "retry: 2000\n\n"
        if st is None:  # finished before this process started (or another instance)
            yield f"data: {json.dumps({'event': 'done', 'status': run.status.value})}\n\n"
            return
        i, deadline = 0, time.monotonic() + 600
        while time.monotonic() < deadline:
            with st.cond:
                if i >= len(st.events) and not st.done:
                    st.cond.wait(timeout=15)
                batch = st.events[i:]
                i = len(st.events)
                finished = st.done
            for ev in batch:
                yield f"data: {json.dumps(ev, default=str)}\n\n"
            if finished and not batch:
                return
            if not batch:
                yield ": keep-alive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ editing
@router.patch("/{tid}/entries/{eid}")
def move_entry(tid: str, eid: str, body: MoveIn, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    tt = svc.get_timetable(db, tid)
    e, _ = svc.move_entry(db, tt, eid, day=body.day, start_period=body.start_period, room_id=body.room_id,
                          expected_version=body.expected_version)
    audit.record(db, action="timetable.entry_move", category="TIMETABLE", actor=p.user, entity="timetable",
                 entity_id=tt.id, ctx=p.ctx, summary=f"Moved a session in '{tt.name}'",
                 data={"entry_id": eid, "to": [body.day, body.start_period, e.room_id]})
    db.commit()
    return {"summary": svc.timetable_summary(tt), "entry_id": e.id}


@router.get("/{tid}/entries/{eid}/options")
def entry_options(tid: str, eid: str, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    return svc.move_options(db, svc.get_timetable(db, tid), eid)


@router.post("/{tid}/lock")
def lock_entries(tid: str, body: LockIn, p: Principal = Depends(_edit), db: Session = Depends(get_db)):
    tt = svc.get_timetable(db, tid)
    n = svc.set_lock(tt, body.entry_ids, body.locked)
    audit.record(db, action="timetable.lock" if body.locked else "timetable.unlock", category="TIMETABLE",
                 actor=p.user, entity="timetable", entity_id=tt.id, ctx=p.ctx,
                 summary=f"{'Locked' if body.locked else 'Unlocked'} {n} session(s) in '{tt.name}'")
    db.commit()
    return {"changed": n, "summary": svc.timetable_summary(tt)}


# ------------------------------------------------------------------ review & publish
@router.post("/{tid}/submit")
def submit(tid: str, body: SubmitIn, p: Principal = Depends(require_perm("timetable.submit", "timetable.publish", any_of=True)),
           db: Session = Depends(get_db)):
    tt = svc.get_timetable(db, tid)
    res = workflow.submit_for_publish(db, p, tt, body.note)
    return {"published": res["published"], "request_id": res["request"].id if res["request"] else None,
            "summary": svc.timetable_summary(tt)}


# ------------------------------------------------------------------ export
@router.get("/{tid}/export")
def export(tid: str, format: Literal["pdf", "xlsx", "csv", "ics"] = "pdf",
           by: Literal["group", "faculty", "room"] = "group", ref: str | None = None,
           term_start: date | None = None, p: Principal = Depends(require_perm("timetable.export")),
           db: Session = Depends(get_db)):
    tt = _visible(p, svc.get_timetable(db, tid))
    _check_scope(p, by if ref else None, ref)
    v = svc.view(db, tt, by=by if ref else None, ref=ref)
    if by == "group":
        ids = [ref] if ref else sorted({e["group"]["id"] for e in v["entries"]})
        names = {g.id: g.label for g in db.execute(select(StudentGroup).where(StudentGroup.id.in_(ids))).unique().scalars()}
    elif by == "faculty":
        ids = [ref] if ref else sorted({f["id"] for e in v["entries"] for f in e["faculty"]})
        names = {f.id: f.name for f in db.execute(select(Faculty).where(Faculty.id.in_(ids))).scalars()}
    else:
        ids = [ref] if ref else sorted({e["room"]["id"] for e in v["entries"] if e["room"]})
        names = {r.id: f"{r.code} {r.name}" for r in db.execute(select(Room).where(Room.id.in_(ids))).unique().scalars()}
    groups = sorted(((i, names.get(i, i)) for i in ids), key=lambda x: x[1])
    status_note = "" if tt.status == TimetableStatus.PUBLISHED else f" [{tt.status.value.replace('_', ' ')} — not official]"
    fname = "".join(c if c.isalnum() else "_" for c in tt.name)[:60] or "timetable"
    audit.record(db, action="timetable.export", category="TIMETABLE", actor=p.user, entity="timetable",
                 entity_id=tt.id, ctx=p.ctx, summary=f"Exported '{tt.name}' as {format.upper()}",
                 data={"by": by, "ref": ref})
    db.commit()
    if format == "ics":
        body, media = render.to_ics(v, tt.name, term_start), "text/calendar"
    else:
        sheets = render.build_sheets(v, groups, by)
        if format == "csv":
            body, media = render.to_csv(sheets), "text/csv"
        elif format == "xlsx":
            body, media = render.to_xlsx(sheets, tt.name + status_note), \
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            body, media = render.to_pdf(sheets, tt.name + status_note,
                                        f"Generated by NFSU Timetable System · {tt.status.value.title()}"), "application/pdf"
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}.{format}"'})


# ------------------------------------------------------------------ requests (maker–checker)
def _req_dict(cr) -> dict:
    return {"id": cr.id, "kind": cr.kind.value, "status": cr.status.value, "title": cr.title, "reason": cr.reason,
            "payload": cr.payload, "target_type": cr.target_type, "target_id": cr.target_id,
            "reviewer_role": cr.reviewer_role.value,
            "requested_by": {"id": cr.requested_by.id, "name": cr.requested_by.full_name,
                             "role": cr.requested_by.role.value} if cr.requested_by else None,
            "reviewed_by": {"id": cr.reviewed_by.id, "name": cr.reviewed_by.full_name} if cr.reviewed_by else None,
            "review_comment": cr.review_comment, "created_at": cr.created_at.isoformat(),
            "reviewed_at": cr.reviewed_at.isoformat() if cr.reviewed_at else None}


@requests_router.get("")
def list_requests(status: RequestStatus | None = None, mine: bool = False, p: Principal = Depends(_any),
                  db: Session = Depends(get_db)):
    return [_req_dict(r) for r in workflow.list_requests(db, p, status=status, mine=mine)]


@requests_router.post("/{rid}/review")
def review_request(rid: str, body: ReviewIn,
                   p: Principal = Depends(require_perm("requests.review", "timetable.publish", any_of=True)),
                   db: Session = Depends(get_db)):
    return _req_dict(workflow.review(db, p, rid, approve=body.approve, comment=body.comment))


@requests_router.post("/{rid}/cancel")
def cancel_request(rid: str, p: Principal = Depends(_any), db: Session = Depends(get_db)):
    return _req_dict(workflow.cancel(db, p, rid))


@router.post("/{tid}/move-requests", status_code=201)
def request_move(tid: str, body: MoveRequestIn, p: Principal = Depends(require_perm("session.request_move")),
                 db: Session = Depends(get_db)):
    cr = workflow.request_session_move(db, p, tid, body.entry_id, day=body.day, start_period=body.start_period,
                                       reason=body.reason)
    return _req_dict(cr)
