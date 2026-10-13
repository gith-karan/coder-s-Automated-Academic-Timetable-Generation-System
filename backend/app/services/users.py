"""User management with hierarchy enforcement and upward notifications."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import Principal, deny
from app.core.errors import AppError, bad_request, not_found
from app.core.roles import RANK, Role, can_create, can_manage, visible_roles
from app.core.security import generate_temp_password, hash_password
from app.models.academic import Batch, Faculty, StudentGroup
from app.models.identity import User
from app.schemas.identity import UserCreateIn, UserUpdateIn
from app.services import audit, notifications
from app.services.auth import revoke_user_sessions

ROLE_LABEL = {Role.ADMIN: "Admin", Role.COORDINATOR: "Coordinator", Role.FACULTY: "Faculty", Role.STUDENT: "Student"}


def _validate_links(db: Session, role: Role, data: dict) -> None:
    if role == Role.FACULTY and data.get("faculty_id") and db.get(Faculty, data["faculty_id"]) is None:
        raise bad_request("Selected faculty profile does not exist.")
    if role == Role.STUDENT:
        gid, bid = data.get("group_id"), data.get("batch_id")
        if gid and db.get(StudentGroup, gid) is None:
            raise bad_request("Selected class does not exist.")
        if bid:
            b = db.get(Batch, bid)
            if b is None or (gid and b.group_id != gid):
                raise bad_request("Selected batch does not belong to the selected class.")
    if role != Role.FACULTY:
        data["faculty_id"] = None
    if role != Role.STUDENT:
        data["group_id"] = data["batch_id"] = data["enrollment_no"] = None


def create_user(db: Session, p: Principal, body: UserCreateIn) -> tuple[User, str]:
    if not can_create(p.role, body.role):
        raise deny(p, f"{p.role} attempted to create a {body.role} account ({body.email})")
    data = body.model_dump()
    _validate_links(db, body.role, data)
    temp = generate_temp_password()
    user = User(email=str(body.email).lower(), username=(body.username or None), full_name=body.full_name,
                role=body.role, password_hash=hash_password(temp), must_change_password=True,
                created_by_id=p.user.id, faculty_id=data["faculty_id"], enrollment_no=data["enrollment_no"],
                group_id=data["group_id"], batch_id=data["batch_id"])
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "duplicate", "A user with this email, username or enrollment number already exists.") from exc
    audit.record(db, action="user.create", category="USER", actor=p.user, entity="user", entity_id=user.id, ctx=p.ctx,
                 summary=f"{ROLE_LABEL[p.role]} {p.user.full_name} added {ROLE_LABEL[user.role].lower()} "
                         f"{user.full_name} ({user.email})",
                 data={"role": user.role.value, "email": user.email})
    notifications.notify_superiors(
        db, p.user, kind="user_added",
        title=f"New {ROLE_LABEL[user.role].lower()} added",
        body=f"{p.user.full_name} ({ROLE_LABEL[p.role]}) added {user.full_name} <{user.email}> as "
             f"{ROLE_LABEL[user.role]}.",
        link=f"/users?highlight={user.id}", data={"user_id": user.id, "added_by": p.user.id})
    db.commit()
    db.refresh(user)
    return user, temp


def list_users(db: Session, p: Principal, *, q: str | None, role: Role | None, page: int, size: int) -> dict:
    roles = visible_roles(p.role)
    if role is not None:
        if role not in roles:
            return {"items": [], "total": 0, "page": page, "size": size}
        roles = [role]
    stmt = select(User).where(User.role.in_(roles))
    if p.role == Role.FACULTY:  # faculty only see the students they added
        stmt = stmt.where(User.created_by_id == p.user.id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(User.full_name).like(like) | func.lower(User.email).like(like))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)).unique().scalars().all()
    return {"items": rows, "total": total, "page": page, "size": size}


def _get_manageable(db: Session, p: Principal, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    if user.id == p.user.id:
        raise bad_request("Use your profile page to change your own account.")
    if not can_manage(p.role, user.role) or (p.role == Role.FACULTY and user.created_by_id != p.user.id):
        raise deny(p, f"{p.role} attempted to manage {user.role} {user.email}")
    return user


def update_user(db: Session, p: Principal, user_id: str, body: UserUpdateIn) -> User:
    user = _get_manageable(db, p, user_id)
    data = body.model_dump(exclude_unset=True)
    new_role = data.get("role", user.role)
    if "role" in data and not can_create(p.role, new_role):
        raise deny(p, f"{p.role} attempted to change {user.email} to role {new_role}")
    if user.role == Role.ADMIN and (new_role != Role.ADMIN or data.get("is_active") is False):
        active_admins = db.execute(select(func.count()).select_from(User).where(
            User.role == Role.ADMIN, User.is_active.is_(True))).scalar_one()
        if active_admins <= 1:
            raise bad_request("The last active admin cannot be demoted or deactivated.")
    links = {k: data.get(k, getattr(user, k)) for k in ("faculty_id", "group_id", "batch_id", "enrollment_no")}
    _validate_links(db, new_role, links)
    before = {"role": user.role.value, "is_active": user.is_active, "full_name": user.full_name}
    for k in ("full_name", "role", "is_active"):
        if k in data:
            setattr(user, k, data[k])
    for k, v in links.items():
        setattr(user, k, v)
    if data.get("is_active") is False or ("role" in data and RANK[new_role] < RANK[Role(before["role"])]):
        revoke_user_sessions(db, user.id)  # privilege reduced -> kill existing sessions
    after = {"role": user.role.value, "is_active": user.is_active, "full_name": user.full_name}
    action = "user.deactivate" if before["is_active"] and not user.is_active else "user.update"
    audit.record(db, action=action, category="USER", actor=p.user, entity="user", entity_id=user.id, ctx=p.ctx,
                 summary=f"{p.user.full_name} updated {user.full_name} ({user.email})",
                 data={"before": before, "after": after})
    if action == "user.deactivate" or before["role"] != after["role"]:
        notifications.notify_superiors(db, p.user, kind="user_changed", title="User account changed",
                                       body=f"{p.user.full_name} changed {user.full_name}: {before} → {after}",
                                       link=f"/users?highlight={user.id}")
    db.commit()
    db.refresh(user)
    return user


def reset_password(db: Session, p: Principal, user_id: str) -> str:
    user = _get_manageable(db, p, user_id)
    temp = generate_temp_password()
    user.password_hash = hash_password(temp)
    user.must_change_password = True
    user.failed_logins, user.locked_until = 0, None
    revoke_user_sessions(db, user.id)
    audit.record(db, action="user.reset_password", category="SECURITY", actor=p.user, entity="user", entity_id=user.id,
                 ctx=p.ctx, summary=f"{p.user.full_name} reset the password of {user.email}")
    notifications.notify_superiors(db, p.user, kind="security", title="Password reset",
                                   body=f"{p.user.full_name} reset the password of {user.full_name} <{user.email}>.")
    db.commit()
    return temp
