"""Maker–checker workflow.

* Faculty availability change  -> coordinator/admin approves (if the setting requires it)
* Faculty session-move request -> coordinator/admin approves; applied to a new draft revision
* Coordinator publish request   -> admin approves (if the setting requires it)

Rules: the requester can never approve their own request (separation of duties); every step is
audited and the relevant people are notified.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, deny
from app.core.db import utcnow
from app.core.errors import AppError, bad_request, conflict, not_found
from app.core.roles import RANK, Role
from app.models.academic import Faculty
from app.models.identity import User
from app.models.timetable import Timetable, TimetableEntry, TimetableStatus
from app.models.workflow import ChangeRequest, RequestKind, RequestStatus
from app.scheduling.validator import hard, validate
from app.services import audit, notifications
from app.services import permissions as perm_service
from app.services.timetables import check_move, content_hash, placements_of, problem_for, unique_name

# ------------------------------------------------------------------ helpers


def _pending_exists(db: Session, kind: RequestKind, target_id: str) -> ChangeRequest | None:
    return db.execute(select(ChangeRequest).where(ChangeRequest.kind == kind, ChangeRequest.target_id == target_id,
                                                  ChangeRequest.status == RequestStatus.PENDING)).scalars().first()


def _subject_label(db: Session, subject_id: str) -> str:
    from app.models.academic import Subject

    s = db.get(Subject, subject_id)
    return f"{s.short_name or s.code} ({s.code})" if s else "a session"


def _reviewers(db: Session, kind: RequestKind, requester: User) -> list[User]:
    perm = "timetable.publish" if kind == RequestKind.TIMETABLE_PUBLISH else "requests.review"
    return [u for u in perm_service.users_with(db, perm)
            if u.id != requester.id and (u.role == Role.ADMIN or RANK[u.role] > RANK[requester.role])]


def _create(db: Session, p: Principal, *, kind: RequestKind, reviewer: Role, target_type: str, target_id: str,
            title: str, reason: str, payload: dict, link: str) -> ChangeRequest:
    cr = ChangeRequest(kind=kind, reviewer_role=reviewer, target_type=target_type, target_id=target_id, title=title,
                       reason=reason, payload=payload, requested_by_id=p.user.id)
    db.add(cr)
    db.flush()
    audit.record(db, action=f"request.{kind.value.lower()}.submit", category="WORKFLOW", actor=p.user,
                 entity="change_request", entity_id=cr.id, ctx=p.ctx, summary=title, data={"reason": reason})
    notifications.notify(db, _reviewers(db, kind, p.user), kind="approval_request", title=title,
                         body=f"{p.user.full_name} requests approval. {reason}".strip(), link=link,
                         data={"request_id": cr.id}, exclude_id=p.user.id)
    return cr


# ------------------------------------------------------------------ availability


def apply_availability(db: Session, faculty: Faculty, availability: dict) -> None:
    faculty.availability = availability


def request_availability(db: Session, p: Principal, faculty_id: str, availability: dict, reason: str) -> dict:
    fac = db.get(Faculty, faculty_id)
    if fac is None:
        raise not_found("Faculty")
    own = p.user.faculty_id == faculty_id
    direct = p.can("setup.edit") or (own and p.can("availability.edit_own"))
    if not direct and not (own and p.can("availability.request")):
        raise deny(p, f"{p.user.email} tried to change availability of faculty {fac.code}")
    if direct:
        before = fac.availability
        apply_availability(db, fac, availability)
        audit.record(db, action="faculty.availability.update", category="DATA", actor=p.user, entity="faculty",
                     entity_id=fac.id, ctx=p.ctx, summary=f"Availability of {fac.name} updated",
                     data={"before": before, "after": availability})
        db.commit()
        return {"applied": True, "request": None}
    if _pending_exists(db, RequestKind.AVAILABILITY, fac.id):
        raise conflict("You already have a pending availability request. Cancel it before sending a new one.")
    cr = _create(db, p, kind=RequestKind.AVAILABILITY, reviewer=Role.COORDINATOR, target_type="faculty",
                 target_id=fac.id, title=f"Availability change for {fac.name}", reason=reason,
                 payload={"availability": availability, "before": fac.availability}, link="/requests")
    db.commit()
    return {"applied": False, "request": cr}


# ------------------------------------------------------------------ session move


def request_session_move(db: Session, p: Principal, timetable_id: str, entry_id: str, *, day: int, start_period: int,
                         reason: str) -> ChangeRequest:
    tt = db.get(Timetable, timetable_id)
    if tt is None or tt.status != TimetableStatus.PUBLISHED:
        raise bad_request("Changes can only be requested on a published timetable.")
    e = next((x for x in tt.entries if x.id == entry_id), None)
    if e is None:
        raise not_found("Session")
    if p.role == Role.FACULTY and p.user.faculty_id not in (e.faculty_ids or []):
        raise deny(p, f"{p.user.email} requested a move of a session they do not teach")
    problem = problem_for(db, tt, keep_locked=False)
    violations = check_move(problem, placements_of(tt), e.session_key, day, start_period, e.room_id or "")
    if violations:
        raise AppError(409, "conflict", f"That slot is not possible: {violations[0].message}",
                       extra={"violations": [v.to_dict() for v in violations]})
    cr = _create(db, p, kind=RequestKind.SESSION_MOVE, reviewer=Role.COORDINATOR, target_type="timetable",
                 target_id=tt.id,
                 title=f"Move request: {_subject_label(db, e.subject_id)} in {tt.name}",
                 reason=reason, payload={"entry_id": entry_id, "session_key": e.session_key, "from":
                                         [e.day, e.start_period], "to": [day, start_period]}, link="/requests")
    db.commit()
    return cr


def duplicate(db: Session, tt: Timetable, actor: User, name: str | None = None) -> Timetable:
    copy = Timetable(name=name or unique_name(db, tt.name), academic_year=tt.academic_year, term=tt.term,
                     programme_ids=list(tt.programme_ids or []),
                     semesters=list(tt.semesters or []), parent_id=tt.id, created_by_id=actor.id,
                     quality_score=tt.quality_score, is_complete=tt.is_complete)
    db.add(copy)
    db.flush()
    for e in tt.entries:
        copy.entries.append(TimetableEntry(
            timetable_id=copy.id, session_key=e.session_key, subject_id=e.subject_id, group_id=e.group_id,
            batch_id=e.batch_id, faculty_ids=list(e.faculty_ids or []), room_id=e.room_id, day=e.day,
            start_period=e.start_period, length=e.length, locked=e.locked))
    db.flush()
    return copy


# ------------------------------------------------------------------ publish


def publish(db: Session, tt: Timetable, actor: User, ctx) -> Timetable:
    problem = problem_for(db, tt)
    violations = hard(validate(problem, placements_of(tt)))
    if violations:
        raise AppError(409, "not_publishable", "This timetable still breaks mandatory rules and cannot be published.",
                       extra={"violations": [v.to_dict() for v in violations[:50]]})
    scope_groups = {e.group_id for e in tt.entries}
    for other in db.execute(select(Timetable).where(Timetable.status == TimetableStatus.PUBLISHED,
                                                    Timetable.id != tt.id)).scalars():
        if scope_groups & {e.group_id for e in other.entries}:
            # Only one live version per class: the previous one becomes an ordinary draft again.
            other.status = TimetableStatus.DRAFT
            other.notice = f"Unpublished on {utcnow():%d %b %Y}: replaced by '{tt.name}'."
            other.row_version += 1
            audit.record(db, action="timetable.unpublish", category="TIMETABLE", actor=actor, entity="timetable",
                         entity_id=other.id, ctx=ctx, summary=f"'{other.name}' unpublished (replaced by '{tt.name}')")
    tt.status = TimetableStatus.PUBLISHED
    tt.notice = None
    tt.published_at, tt.published_by_id = utcnow(), actor.id
    tt.content_hash = content_hash(tt)
    tt.is_complete = True
    audit.record(db, action="timetable.publish", category="TIMETABLE", actor=actor, entity="timetable",
                 entity_id=tt.id, ctx=ctx, summary=f"Published '{tt.name}'", data={"content_hash": tt.content_hash})
    notifications.notify_roles(db, list(Role), kind="timetable_published", title="New timetable published",
                               body=f"'{tt.name}' is now live. Check your updated schedule.",
                               link=f"/timetable?tt={tt.id}", exclude_id=actor.id)
    return tt


def submit_for_publish(db: Session, p: Principal, tt: Timetable, note: str) -> dict:
    if tt.status != TimetableStatus.DRAFT:
        raise conflict("Only draft timetables can be submitted.")
    problem = problem_for(db, tt)
    violations = hard(validate(problem, placements_of(tt)))
    if violations:
        raise AppError(409, "not_publishable", "Fix all conflicts and unassigned sessions before publishing.",
                       extra={"violations": [v.to_dict() for v in violations[:50]]})
    if p.can("timetable.publish"):
        publish(db, tt, p.user, p.ctx)
        db.commit()
        return {"published": True, "request": None}
    tt.status = TimetableStatus.IN_REVIEW
    tt.submitted_by_id, tt.submitted_at, tt.review_comment = p.user.id, utcnow(), None
    cr = _create(db, p, kind=RequestKind.TIMETABLE_PUBLISH, reviewer=Role.ADMIN, target_type="timetable",
                 target_id=tt.id, title=f"Publish request: {tt.name}", reason=note,
                 payload={"content_hash": content_hash(tt)}, link=f"/timetable?tt={tt.id}")
    db.commit()
    return {"published": False, "request": cr}


# ------------------------------------------------------------------ review


def review(db: Session, p: Principal, request_id: str, *, approve: bool, comment: str) -> ChangeRequest:
    cr = db.get(ChangeRequest, request_id)
    if cr is None:
        raise not_found("Request")
    if cr.status != RequestStatus.PENDING:
        raise conflict(f"This request was already {cr.status.value.lower()}.")
    needed = "timetable.publish" if cr.kind == RequestKind.TIMETABLE_PUBLISH else "requests.review"
    requester_role = cr.requested_by.role if cr.requested_by else Role.STUDENT
    if not p.can(needed) or (p.role != Role.ADMIN and RANK[p.role] <= RANK[requester_role]):
        raise deny(p, f"{p.role} attempted to review {cr.kind} request {cr.id}")
    if cr.requested_by_id == p.user.id:
        raise deny(p, f"{p.user.email} attempted to approve their own request {cr.id}")
    if not approve and not comment.strip():
        raise bad_request("Please give a reason when rejecting a request.")

    result_link = None
    if approve:
        if cr.kind == RequestKind.AVAILABILITY:
            fac = db.get(Faculty, cr.target_id)
            if fac is None:
                raise not_found("Faculty")
            apply_availability(db, fac, cr.payload["availability"])
        elif cr.kind == RequestKind.TIMETABLE_PUBLISH:
            tt = db.get(Timetable, cr.target_id)
            if tt is None or tt.status != TimetableStatus.IN_REVIEW:
                raise conflict("The timetable is no longer awaiting review.")
            if content_hash(tt) != cr.payload.get("content_hash"):
                raise conflict("The timetable changed after it was submitted. Ask for it to be resubmitted.")
            publish(db, tt, p.user, p.ctx)
            result_link = f"/timetable?tt={tt.id}"
        elif cr.kind == RequestKind.SESSION_MOVE:
            src = db.get(Timetable, cr.target_id)
            if src is None:
                raise not_found("Timetable")
            draft = duplicate(db, src, p.user)
            entry = next(e for e in draft.entries if e.session_key == cr.payload["session_key"])
            problem = problem_for(db, draft, keep_locked=False)
            day, period = cr.payload["to"]
            v = check_move(problem, placements_of(draft), entry.session_key, day, period, entry.room_id or "")
            if v:
                db.rollback()
                raise AppError(409, "conflict", f"The requested slot is no longer free: {v[0].message}")
            entry.day, entry.start_period = day, period
            cr.payload = {**cr.payload, "draft_id": draft.id}
            result_link = f"/timetable?tt={draft.id}"
    else:
        if cr.kind == RequestKind.TIMETABLE_PUBLISH:
            tt = db.get(Timetable, cr.target_id)
            if tt is not None and tt.status == TimetableStatus.IN_REVIEW:
                tt.status, tt.review_comment = TimetableStatus.DRAFT, comment

    cr.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
    cr.reviewed_by_id, cr.reviewed_at, cr.review_comment = p.user.id, utcnow(), comment or None
    verdict = "approved" if approve else "rejected"
    audit.record(db, action=f"request.{cr.kind.value.lower()}.{verdict}", category="WORKFLOW", actor=p.user,
                 entity="change_request", entity_id=cr.id, ctx=p.ctx, summary=f"{cr.title} — {verdict}",
                 data={"comment": comment})
    requester = db.get(User, cr.requested_by_id)
    if requester:
        notifications.notify(db, [requester], kind="approval_result", title=f"Request {verdict}: {cr.title}",
                             body=f"{p.user.full_name} {verdict} your request. {comment}".strip(),
                             link=result_link or "/requests", data={"request_id": cr.id})
    notifications.notify_superiors(db, p.user, kind="approval_result", title=f"{cr.title} — {verdict}",
                                   body=f"{p.user.full_name} {verdict} a request from "
                                        f"{requester.full_name if requester else 'a user'}.", link="/requests")
    db.commit()
    return cr


def cancel(db: Session, p: Principal, request_id: str) -> ChangeRequest:
    cr = db.get(ChangeRequest, request_id)
    if cr is None:
        raise not_found("Request")
    if cr.requested_by_id != p.user.id:
        raise deny(p, f"{p.user.email} attempted to cancel someone else's request {cr.id}")
    if cr.status != RequestStatus.PENDING:
        raise conflict("Only pending requests can be cancelled.")
    cr.status = RequestStatus.CANCELLED
    if cr.kind == RequestKind.TIMETABLE_PUBLISH:
        tt = db.get(Timetable, cr.target_id)
        if tt is not None and tt.status == TimetableStatus.IN_REVIEW:
            tt.status = TimetableStatus.DRAFT
    audit.record(db, action=f"request.{cr.kind.value.lower()}.cancel", category="WORKFLOW", actor=p.user,
                 entity="change_request", entity_id=cr.id, ctx=p.ctx, summary=f"{cr.title} — cancelled")
    db.commit()
    return cr


def list_requests(db: Session, p: Principal, *, status: RequestStatus | None, mine: bool) -> list[ChangeRequest]:
    stmt = select(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(ChangeRequest.status == status)
    kinds = []
    if p.can("requests.review"):
        kinds += [RequestKind.AVAILABILITY, RequestKind.SESSION_MOVE]
    if p.can("timetable.publish"):
        kinds.append(RequestKind.TIMETABLE_PUBLISH)
    if mine or not kinds:
        stmt = stmt.where(ChangeRequest.requested_by_id == p.user.id)
    else:
        stmt = stmt.where(ChangeRequest.kind.in_(kinds) | (ChangeRequest.requested_by_id == p.user.id))
    return list(db.execute(stmt).unique().scalars())
