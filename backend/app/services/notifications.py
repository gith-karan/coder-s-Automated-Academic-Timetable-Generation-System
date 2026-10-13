"""In-app notifications with hierarchy-based routing."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import RANK, Role, roles_above
from app.models.identity import Notification, User


def _active_with_roles(db: Session, roles: list[Role]) -> list[User]:
    if not roles:
        return []
    return list(db.execute(select(User).where(User.role.in_(roles), User.is_active.is_(True))).scalars())


def notify(db: Session, recipients: list[User], *, kind: str, title: str, body: str = "",
           link: str | None = None, data: dict | None = None, exclude_id: str | None = None) -> int:
    n = 0
    for r in {u.id: u for u in recipients}.values():
        if r.id == exclude_id:
            continue
        db.add(Notification(recipient_id=r.id, kind=kind, title=title, body=body, link=link, data=data or {}))
        n += 1
    return n


def notify_superiors(db: Session, actor: User, *, kind: str, title: str, body: str = "",
                     link: str | None = None, data: dict | None = None) -> int:
    """Notify every active user whose role ranks strictly above the actor's role.

    Faculty adds a student   -> coordinators and admins.
    Coordinator adds faculty -> admins.
    Admin acts               -> other admins (so admin actions are never invisible).
    """
    roles = roles_above(actor.role) or ([Role.ADMIN] if actor.role == Role.ADMIN else [])
    return notify(db, _active_with_roles(db, roles), kind=kind, title=title, body=body, link=link, data=data,
                  exclude_id=actor.id)


def notify_roles(db: Session, roles: list[Role], *, kind: str, title: str, body: str = "",
                 link: str | None = None, data: dict | None = None, exclude_id: str | None = None) -> int:
    return notify(db, _active_with_roles(db, roles), kind=kind, title=title, body=body, link=link, data=data,
                  exclude_id=exclude_id)


def rank(role: Role) -> int:
    return RANK[role]
