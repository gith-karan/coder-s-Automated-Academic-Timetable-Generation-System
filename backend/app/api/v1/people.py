"""Users, notifications, audit log."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, require_perm
from app.core.db import get_db, utcnow
from app.core.roles import Role
from app.models.audit import AuditLog
from app.models.identity import Notification
from app.schemas.identity import AuditOut, NotificationOut, UserCreatedOut, UserCreateIn, UserOut, UserUpdateIn
from app.services import audit
from app.services import users as user_service

router = APIRouter()

# ------------------------------------------------------------------ users
users = APIRouter(prefix="/users", tags=["users"])
# Role ceilings (e.g. faculty may add students only) are enforced in the service on top of these.
_view_users = require_perm("users.view")
_create_users = require_perm("users.create")
_manage_users = require_perm("users.manage")


@users.get("")
def list_users(q: str | None = Query(None, max_length=100), role: Role | None = None,
               page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
               p: Principal = Depends(_view_users), db: Session = Depends(get_db)):
    res = user_service.list_users(db, p, q=q, role=role, page=page, size=size)
    res["items"] = [UserOut.model_validate(u).model_dump(mode="json") for u in res["items"]]
    return res


@users.post("", response_model=UserCreatedOut, status_code=201)
def create_user(body: UserCreateIn, p: Principal = Depends(_create_users), db: Session = Depends(get_db)):
    user, temp = user_service.create_user(db, p, body)
    out = UserCreatedOut.model_validate({**UserOut.model_validate(user).model_dump(), "temporary_password": temp})
    return out


@users.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdateIn, p: Principal = Depends(_manage_users), db: Session = Depends(get_db)):
    return user_service.update_user(db, p, user_id, body)


@users.post("/{user_id}/reset-password")
def reset_password(user_id: str, p: Principal = Depends(_manage_users), db: Session = Depends(get_db)):
    return {"temporary_password": user_service.reset_password(db, p, user_id)}


# ------------------------------------------------------------------ notifications
notes = APIRouter(prefix="/notifications", tags=["notifications"])


@notes.get("")
def my_notifications(unread_only: bool = False, limit: int = Query(30, ge=1, le=100),
                     p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.recipient_id == p.user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit)).scalars().all()
    unread = db.execute(select(func.count()).select_from(Notification).where(
        Notification.recipient_id == p.user.id, Notification.read_at.is_(None))).scalar_one()
    return {"items": [NotificationOut.model_validate(n).model_dump(mode="json") for n in items], "unread": unread}


@notes.post("/{nid}/read", status_code=204)
def mark_read(nid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.id == nid, Notification.recipient_id == p.user.id,
                                          Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
    return Response(status_code=204)


@notes.post("/read-all", status_code=204)
def mark_all_read(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.recipient_id == p.user.id, Notification.read_at.is_(None))
               .values(read_at=utcnow()))
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ audit (admin only, read-only)
audit_router = APIRouter(prefix="/audit-logs", tags=["audit"])
_admin = require_perm("audit.view")


@audit_router.get("")
def list_audit(q: str | None = Query(None, max_length=100), category: str | None = Query(None, max_length=24),
               outcome: str | None = Query(None, max_length=12), actor_id: str | None = None,
               since: datetime | None = None, until: datetime | None = None,
               page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
               p: Principal = Depends(_admin), db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(AuditLog.summary).like(like) | func.lower(AuditLog.action).like(like)
                          | func.lower(AuditLog.actor_email).like(like))
    if category:
        stmt = stmt.where(AuditLog.category == category)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if since:
        stmt = stmt.where(AuditLog.at >= since)
    if until:
        stmt = stmt.where(AuditLog.at <= until)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(AuditLog.seq.desc()).offset((page - 1) * size).limit(size)).scalars().all()
    return {"items": [AuditOut.model_validate(r).model_dump(mode="json") for r in rows], "total": total,
            "page": page, "size": size}


@audit_router.get("/verify")
def verify(p: Principal = Depends(_admin), db: Session = Depends(get_db)):
    result = audit.verify_chain(db)
    audit.record(db, action="audit.verify", category="SECURITY", actor=p.user, ctx=p.ctx,
                 outcome="SUCCESS" if result["ok"] else "FAILURE", summary=result["message"])
    db.commit()
    return result


router.include_router(users)
router.include_router(notes)
router.include_router(audit_router)
