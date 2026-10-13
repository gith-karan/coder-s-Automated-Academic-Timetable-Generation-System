"""Development-only helpers (never mounted in production): load demo data, toggle the PS §3 scenario."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, require_roles
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import conflict, not_found
from app.core.roles import Role
from app.models.academic import Faculty
from app.seed import is_seeded, seed_demo
from app.services import audit

router = APIRouter(prefix="/demo", tags=["demo"])
_admin = require_roles(Role.ADMIN, Role.COORDINATOR)


@router.post("/seed")
def seed(p: Principal = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if is_seeded(db):
        raise conflict("Demo data is already loaded.")
    return seed_demo(db, actor=p.user, demo_password=get_settings().demo_password)


@router.post("/scenario/{name}")
def scenario(name: str, p: Principal = Depends(_admin), db: Session = Depends(get_db)):
    """'infeasible': Dr. Vijeta Khare (MTAI26-PC-102 NSF) is available for only 2 periods — the PS §3
    example. 'reset': available all week again."""
    f = db.execute(select(Faculty).where(Faculty.code == "VK")).scalar_one_or_none()
    if f is None:
        raise not_found("Faculty VK (load the SCSDF data first)")
    if name == "infeasible":
        f.availability = {"available": [{"day": 0, "start": "10:30", "end": "11:30"},
                                        {"day": 2, "start": "10:30", "end": "11:30"}]}
    elif name == "reset":
        f.availability = {}
    else:
        raise not_found("Scenario")
    audit.record(db, action="demo.scenario", category="DATA", actor=p.user, entity="faculty", entity_id=f.id,
                 ctx=p.ctx, summary=f"Applied demo scenario '{name}' to {f.name}")
    db.commit()
    return {"scenario": name, "faculty": f.name}
