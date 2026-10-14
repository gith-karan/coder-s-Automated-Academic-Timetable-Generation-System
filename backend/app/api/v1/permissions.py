"""Roles & permissions: who may see and do what, with hierarchical delegation (see app.core.permissions)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, deny
from app.core import permissions as P
from app.core.db import get_db
from app.core.errors import bad_request
from app.core.roles import Role
from app.schemas.common import StrictModel
from app.services import audit, notifications
from app.services import permissions as perm_service

router = APIRouter(prefix="/permissions", tags=["permissions"])


def _view(db: Session, p: Principal) -> dict:
    return {
        "catalogue": P.catalogue_dicts(),
        "matrix": perm_service.matrix(db),
        "editable_roles": [r.value for r in P.manageable_roles(p.role, p.perms)],
        "my_permissions": sorted(p.perms),
    }


@router.get("")
def get_permissions(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if p.role != Role.ADMIN and not p.can("permissions.manage"):
        raise deny(p, f"{p.role} tried to read the permission matrix")
    return _view(db, p)


class RolePermissionsIn(StrictModel):
    permissions: Annotated[list[str], Field(max_length=len(P.CATALOGUE))]


@router.put("/{role}")
def set_role_permissions(role: Role, body: RolePermissionsIn, p: Principal = Depends(current_principal),
                         db: Session = Depends(get_db)):
    if role not in P.manageable_roles(p.role, p.perms):
        raise deny(p, f"{p.role} tried to change permissions of {role}")
    unknown = [k for k in body.permissions if k not in P.BY_KEY]
    if unknown:
        raise bad_request(f"Unknown permission(s): {', '.join(unknown[:5])}")
    above_ceiling = [P.BY_KEY[k].label for k in body.permissions if not P.BY_KEY[k].allowed_for(role)]
    if above_ceiling:
        raise bad_request(f"{role.title()} can never hold: {', '.join(above_ceiling)}.")
    before = set(perm_service.matrix(db)[role.value])
    after = set(body.permissions)
    changed = before ^ after
    not_mine = [P.BY_KEY[k].label for k in changed if k not in p.perms]
    if not_mine:
        raise deny(p, f"{p.role} tried to change permissions they do not hold: {', '.join(not_mine)}")
    saved = perm_service.save_role(db, role, sorted(after))
    added, removed = sorted(after - before), sorted(before - after)
    audit.record(db, action="permissions.update", category="SECURITY", actor=p.user, entity="role",
                 entity_id=role.value, ctx=p.ctx,
                 summary=f"{p.user.full_name} changed {role.value.title()} permissions "
                         f"(+{len(added)} / -{len(removed)})", data={"added": added, "removed": removed})
    if added or removed:
        labels = [f"+ {P.BY_KEY[k].label}" for k in added] + [f"− {P.BY_KEY[k].label}" for k in removed]
        notifications.notify_superiors(db, p.user, kind="security", title=f"{role.value.title()} permissions changed",
                                       body=f"{p.user.full_name}: " + "; ".join(labels), link="/settings?tab=permissions")
    db.commit()
    return {"role": role.value, "permissions": saved, **_view(db, p)}
