"""Role hierarchy and the policy for who may create/manage whom.

    ADMIN  >  COORDINATOR  >  FACULTY  >  STUDENT

* ADMIN may create and manage users of any role.
* Any other role may only create/manage users of a strictly lower role, restricted further by
  ``CREATABLE_ROLES`` (faculty may only add students).
* When a user is added by someone, every active user whose role is strictly higher than the
  creator's role is notified (faculty adds student -> coordinators + admins are notified;
  coordinator adds faculty -> admins are notified).
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    COORDINATOR = "COORDINATOR"
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"


RANK: dict[Role, int] = {Role.ADMIN: 40, Role.COORDINATOR: 30, Role.FACULTY: 20, Role.STUDENT: 10}

CREATABLE_ROLES: dict[Role, frozenset[Role]] = {
    Role.ADMIN: frozenset(Role),
    Role.COORDINATOR: frozenset({Role.FACULTY, Role.STUDENT}),
    Role.FACULTY: frozenset({Role.STUDENT}),
    Role.STUDENT: frozenset(),
}


def can_create(actor: Role, target: Role) -> bool:
    return target in CREATABLE_ROLES[actor]


def can_manage(actor: Role, target: Role) -> bool:
    """Edit / deactivate / reset password of an existing user."""
    if actor == Role.ADMIN:
        return True
    return target in CREATABLE_ROLES[actor] and RANK[target] < RANK[actor]


def roles_above(role: Role) -> list[Role]:
    return [r for r in Role if RANK[r] > RANK[role]]


def visible_roles(actor: Role) -> list[Role]:
    """Which user roles an actor may list."""
    if actor == Role.ADMIN:
        return list(Role)
    return sorted(CREATABLE_ROLES[actor], key=lambda r: -RANK[r])


# Permission groups used by route dependencies (deny by default).
STAFF = (Role.ADMIN, Role.COORDINATOR)
TEACHING = (Role.ADMIN, Role.COORDINATOR, Role.FACULTY)
EVERYONE = tuple(Role)
