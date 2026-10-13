"""Append-only, hash-chained audit trail (see app.models.audit for the integrity design)."""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal, utcnow
from app.models.audit import GENESIS_HASH, AuditChainHead, AuditLog

_SENSITIVE = {"password", "password_hash", "new_password", "current_password", "token", "token_hash",
              "csrf_hash", "code", "code_hash", "mfa_secret", "temp_password", "secret"}


@dataclass(frozen=True)
class RequestCtx:
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


def scrub(value: Any) -> Any:
    """Remove secrets and make the value JSON-safe."""
    if isinstance(value, dict):
        return {str(k): ("***" if str(k).lower() in _SENSITIVE else scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [scrub(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _epoch_us(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000)


def _digest(prev_hash: str, row: AuditLog) -> str:
    payload = {
        "at": _epoch_us(row.at), "actor_id": row.actor_id, "actor_email": row.actor_email, "actor_role": row.actor_role,
        "action": row.action, "category": row.category, "outcome": row.outcome, "entity": row.entity,
        "entity_id": row.entity_id, "summary": row.summary, "data": row.data, "ip": row.ip,
        "user_agent": row.user_agent, "request_id": row.request_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    key = get_settings().audit_hmac_key.encode()
    return hmac.new(key, (prev_hash + canonical).encode(), hashlib.sha256).hexdigest()


def record(db: Session, *, action: str, category: str, actor=None, outcome: str = "SUCCESS",
           entity: str | None = None, entity_id: str | None = None, summary: str = "",
           data: dict | None = None, ctx: RequestCtx | None = None) -> AuditLog:
    """Append an audit event inside the caller's transaction (atomic with the change it describes)."""
    head = db.execute(select(AuditChainHead).where(AuditChainHead.id == 1).with_for_update()).scalar_one_or_none()
    if head is None:
        head = AuditChainHead(id=1, last_seq=0, last_hash=GENESIS_HASH)
        db.add(head)
        db.flush()
    ctx = ctx or RequestCtx()
    row = AuditLog(
        at=utcnow(),
        actor_id=getattr(actor, "id", None), actor_email=getattr(actor, "email", None),
        actor_role=str(getattr(actor, "role", "")) or None,
        action=action, category=category, outcome=outcome, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None, summary=summary[:2000],
        data=scrub(data or {}), ip=ctx.ip, user_agent=(ctx.user_agent or "")[:256] or None,
        request_id=ctx.request_id, prev_hash=head.last_hash,
    )
    row.hash = _digest(head.last_hash, row)
    db.add(row)
    db.flush()
    head.last_hash = row.hash
    head.last_seq = row.seq
    return row


def record_standalone(**kwargs) -> None:
    """Record an event in its own transaction (e.g. failed logins, denied access)."""
    db = SessionLocal()
    try:
        record(db, **kwargs)
        db.commit()
    finally:
        db.close()


def verify_chain(db: Session) -> dict:
    prev = GENESIS_HASH
    checked = 0
    for row in db.execute(select(AuditLog).order_by(AuditLog.seq)).scalars().yield_per(500):
        if row.prev_hash != prev or _digest(prev, row) != row.hash:
            return {"ok": False, "checked": checked, "first_invalid_seq": row.seq,
                    "message": f"Audit chain broken at event #{row.seq}: the record was altered, removed or reordered."}
        prev = row.hash
        checked += 1
    head = db.get(AuditChainHead, 1)
    if head is not None and head.last_hash != prev:
        return {"ok": False, "checked": checked, "first_invalid_seq": None,
                "message": "Audit chain head does not match the last record: records were removed from the end."}
    return {"ok": True, "checked": checked, "head": prev, "message": f"All {checked} audit events verified intact."}
