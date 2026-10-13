"""Tamper-evident, append-only audit trail.

Integrity layers:
1. The application only ever INSERTs (no update/delete code paths exist).
2. Database triggers reject UPDATE and DELETE on ``audit_logs`` (see ``install_audit_guards``).
3. Every row carries ``hash = HMAC(key, prev_hash || canonical(row))``. Editing, deleting or
   re-ordering any row breaks the chain, which ``GET /audit-logs/verify`` detects. The HMAC key
   lives outside the database, so someone with DB access alone cannot re-forge the chain.
4. In production the DB role used by the app is granted INSERT/SELECT only on this table.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(254))
    actor_role: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)  # AUTH, USER, DATA, TIMETABLE, SECURITY, SYSTEM
    outcome: Mapped[str] = mapped_column(String(12), default="SUCCESS")  # SUCCESS / FAILURE / DENIED
    entity: Mapped[str | None] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    request_id: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class AuditChainHead(Base):
    """Single row holding the latest hash; locked FOR UPDATE to serialise appends."""

    __tablename__ = "audit_chain_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), default=0)
    last_hash: Mapped[str] = mapped_column(String(64))


GENESIS_HASH = "0" * 64


def install_audit_guards(engine: Engine) -> None:
    """Create DB-level triggers that make audit_logs append-only."""
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            for op in ("UPDATE", "DELETE"):
                conn.execute(text(f"""
                    CREATE TRIGGER IF NOT EXISTS audit_logs_no_{op.lower()}
                    BEFORE {op} ON audit_logs
                    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;
                """))
        elif dialect == "postgresql":
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END; $$ LANGUAGE plpgsql;
            """))
            conn.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_mutation ON audit_logs"))
            conn.execute(text("""
                CREATE TRIGGER audit_logs_no_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_logs
                FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_append_only();
            """))
