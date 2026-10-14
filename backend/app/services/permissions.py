"""Load/save the role-permission matrix and answer "who holds permission X"."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as P
from app.core.roles import Role
from app.models.identity import User
from app.services import system_settings

KEY = "role_permissions"
# Permissions that existed before the "known keys" bookkeeping was introduced.
_LEGACY_KNOWN = P.ALL_KEYS - {"timetable.view_all_classes", "timetable.view_faculty", "timetable.view_rooms"}


def matrix(db: Session) -> dict[str, list[str]]:
    stored = system_settings.get(db, KEY) or {}
    known = set(stored.get("_known") or (_LEGACY_KNOWN if stored else P.ALL_KEYS))
    out: dict[str, list[str]] = {}
    for r in P.MANAGED_ROLES:
        defaults = set(P.DEFAULT_MATRIX[r.value])
        keys = set(stored.get(r.value, defaults))
        # Permissions added after the matrix was last saved start at their default value.
        keys |= {k for k in defaults if k not in known}
        out[r.value] = P.sanitize(r, keys)
    return out


def effective(db: Session, role: Role) -> frozenset[str]:
    return P.effective(role, matrix(db))


def save_role(db: Session, role: Role, keys: list[str]) -> list[str]:
    m = matrix(db)
    m[role.value] = P.sanitize(role, keys)
    system_settings.set_value(db, KEY, {**m, "_known": sorted(P.ALL_KEYS)})
    return m[role.value]


def users_with(db: Session, perm: str) -> list[User]:
    m = matrix(db)
    roles = [r for r in Role if perm in P.effective(r, m)]
    return list(db.execute(select(User).where(User.role.in_(roles), User.is_active.is_(True))).scalars())
