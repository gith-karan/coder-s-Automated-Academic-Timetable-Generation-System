"""First-run bootstrap: create the initial admin account if no admin exists."""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.roles import Role
from app.core.security import generate_temp_password, hash_password
from app.models.identity import User
from app.services import audit

log = logging.getLogger("app.bootstrap")


def ensure_admin() -> None:
    s = get_settings()
    db = SessionLocal()
    try:
        if db.execute(select(User).where(User.role == Role.ADMIN)).scalars().first():
            return
        password = s.bootstrap_admin_password or generate_temp_password()
        admin = User(email=s.bootstrap_admin_email.lower(), username="admin", full_name="System Administrator",
                     role=Role.ADMIN, password_hash=hash_password(password),
                     must_change_password=s.bootstrap_admin_password is None)
        db.add(admin)
        db.flush()
        audit.record(db, action="system.bootstrap_admin", category="SYSTEM", entity="user", entity_id=admin.id,
                     summary=f"Initial administrator {admin.email} created")
        db.commit()
        if s.bootstrap_admin_password is None:
            log.warning("Initial admin created: %s  temporary password: %s  (change it on first sign-in)",
                        admin.email, password)
    finally:
        db.close()
