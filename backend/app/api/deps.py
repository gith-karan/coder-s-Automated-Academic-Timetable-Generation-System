"""Request-scoped dependencies: DB session, request context, authentication, RBAC, CSRF.

Every router is mounted behind ``require_roles(...)`` — access is denied by default.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.middleware import client_ip
from app.core.roles import Role
from app.core.security import constant_time_equals, token_hash
from app.models.identity import AuthSession, User
from app.services import audit
from app.services.audit import RequestCtx
from app.services.auth import resolve_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def request_ctx(request: Request) -> RequestCtx:
    return RequestCtx(ip=client_ip(request), user_agent=request.headers.get("user-agent"),
                      request_id=getattr(request.state, "request_id", None))


@dataclass
class Principal:
    user: User
    session: AuthSession
    ctx: RequestCtx

    @property
    def role(self) -> Role:
        return self.user.role


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    s = get_settings()
    sess = resolve_session(db, request.cookies.get(s.session_cookie))
    if sess is None:
        raise AppError(401, "unauthenticated", "Please sign in to continue.")
    if request.method not in SAFE_METHODS:
        header = request.headers.get("X-CSRF-Token", "")
        if not header or not constant_time_equals(token_hash(header), sess.csrf_hash):
            audit.record_standalone(action="security.csrf_rejected", category="SECURITY", actor=sess.user,
                                    outcome="DENIED", summary=f"Missing/invalid CSRF token on {request.method} "
                                    f"{request.url.path}", ctx=request_ctx(request))
            raise AppError(403, "csrf_failed", "Security token missing or invalid. Refresh the page and try again.")
    request.state.user_id = sess.user_id
    return Principal(sess.user, sess, request_ctx(request))


def require_roles(*roles: Role) -> Callable[..., Principal]:
    allowed = frozenset(roles)

    def _dep(request: Request, p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in allowed:
            audit.record_standalone(action="security.access_denied", category="SECURITY", actor=p.user,
                                    outcome="DENIED", summary=f"{p.role} denied {request.method} {request.url.path}",
                                    ctx=p.ctx)
            raise AppError(403, "forbidden", "You do not have permission to perform this action.")
        if p.user.must_change_password and not request.url.path.endswith(("/auth/me", "/auth/password", "/auth/logout")):
            raise AppError(403, "password_change_required", "Please change your temporary password to continue.")
        return p

    return _dep


def deny(p: Principal, summary: str) -> AppError:
    """Object-level authorisation failure: audit it, return the error to raise."""
    audit.record_standalone(action="security.access_denied", category="SECURITY", actor=p.user, outcome="DENIED",
                            summary=summary, ctx=p.ctx)
    return AppError(403, "forbidden", "You do not have permission to perform this action.")
