"""Authentication: password + email-OTP login, server-side sessions, lockout."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.core.errors import AppError
from app.core.roles import Role
from app.core.security import generate_otp, hash_password, needs_rehash, new_token, token_hash, verify_password
from app.models.identity import AuthSession, OtpChallenge, User
from app.services import audit, notifications
from app.services.audit import RequestCtx
from app.services.mailer import send_mail


def _invalid() -> AppError:
    return AppError(401, "invalid_credentials", "Invalid email/username or password.")


def aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def find_user(db: Session, identifier: str) -> User | None:
    ident = identifier.strip().lower()
    return db.execute(
        select(User).where(or_(func.lower(User.email) == ident, func.lower(User.username) == ident))
    ).scalar_one_or_none()


def _register_failure(db: Session, user: User | None, identifier: str, ctx: RequestCtx, reason: str) -> None:
    s = get_settings()
    if user is not None:
        user.failed_logins += 1
        if user.failed_logins >= s.max_failed_logins:
            user.locked_until = utcnow() + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
            audit.record(db, action="auth.account_locked", category="SECURITY", actor=user, outcome="FAILURE",
                         entity="user", entity_id=user.id, ctx=ctx,
                         summary=f"Account {user.email} locked for {s.lockout_minutes} min after repeated failures")
            notifications.notify_roles(db, [Role.ADMIN], kind="security", title="Account locked",
                                       body=f"{user.email} was locked after repeated failed sign-in attempts.",
                                       link="/audit")
    audit.record(db, action="auth.login", category="AUTH", actor=user, outcome="FAILURE", entity="user",
                 entity_id=getattr(user, "id", None), ctx=ctx, summary=f"Failed sign-in for '{identifier[:80]}'",
                 data={"reason": reason})
    db.commit()


def _check_can_login(db: Session, user: User | None, identifier: str, ctx: RequestCtx) -> User:
    if user is None:
        _register_failure(db, None, identifier, ctx, "unknown_user")
        raise _invalid()
    if not user.is_active:
        _register_failure(db, user, identifier, ctx, "inactive")
        raise _invalid()
    locked = aware(user.locked_until)
    if locked and locked > utcnow():
        audit.record(db, action="auth.login", category="AUTH", actor=user, outcome="DENIED", entity="user",
                     entity_id=user.id, ctx=ctx, summary="Sign-in attempt on locked account")
        db.commit()
        raise AppError(423, "account_locked", "This account is temporarily locked. Try again later.")
    return user


def authenticate(db: Session, identifier: str, password: str, ctx: RequestCtx) -> User:
    user = find_user(db, identifier)
    ok = verify_password(password, user.password_hash if user else None)  # same work even if user is missing
    user = _check_can_login(db, user, identifier, ctx)
    if not ok:
        _register_failure(db, user, identifier, ctx, "bad_password")
        raise _invalid()
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user


def request_otp(db: Session, identifier: str, ctx: RequestCtx) -> None:
    """Behaves identically whether or not the account exists (no user enumeration)."""
    user = find_user(db, identifier)
    if user is None or not user.is_active:
        audit.record(db, action="auth.otp_request", category="AUTH", outcome="FAILURE", ctx=ctx,
                     summary=f"OTP requested for unknown/inactive '{identifier[:80]}'")
        db.commit()
        return
    s = get_settings()
    db.execute(update(OtpChallenge).where(OtpChallenge.user_id == user.id, OtpChallenge.consumed_at.is_(None))
               .values(consumed_at=utcnow()))
    code = generate_otp()
    db.add(OtpChallenge(user_id=user.id, code_hash=token_hash(f"{user.id}:{code}"),
                        expires_at=utcnow() + timedelta(minutes=s.otp_ttl_minutes)))
    audit.record(db, action="auth.otp_request", category="AUTH", actor=user, entity="user", entity_id=user.id,
                 ctx=ctx, summary="One-time sign-in code sent")
    db.commit()
    send_mail(user.email, "Your NFSU Timetable sign-in code",
              f"Your one-time sign-in code is {code}. It expires in {s.otp_ttl_minutes} minutes.\n"
              "If you did not request this code, ignore this email and inform the IT cell.")


def verify_otp(db: Session, identifier: str, code: str, ctx: RequestCtx) -> User:
    user = _check_can_login(db, find_user(db, identifier), identifier, ctx)
    s = get_settings()
    ch = db.execute(select(OtpChallenge).where(OtpChallenge.user_id == user.id, OtpChallenge.consumed_at.is_(None))
                    .order_by(OtpChallenge.created_at.desc())).scalars().first()
    if ch is None or aware(ch.expires_at) < utcnow() or ch.attempts >= s.otp_max_attempts:
        _register_failure(db, user, identifier, ctx, "otp_expired")
        raise AppError(401, "invalid_otp", "The code is invalid or has expired. Request a new one.")
    ch.attempts += 1
    if token_hash(f"{user.id}:{code.strip()}") != ch.code_hash:
        _register_failure(db, user, identifier, ctx, "otp_mismatch")
        raise AppError(401, "invalid_otp", "The code is invalid or has expired. Request a new one.")
    ch.consumed_at = utcnow()
    return user


def start_session(db: Session, user: User, *, remember: bool, ctx: RequestCtx, method: str) -> tuple[str, str]:
    """Create a fresh server-side session (new id on every login prevents session fixation)."""
    s = get_settings()
    token, csrf = new_token(), new_token()
    idle = 24 * 60 if remember else s.session_idle_minutes
    lifetime = timedelta(days=s.remember_me_days) if remember else timedelta(hours=s.session_absolute_hours)
    db.add(AuthSession(token_hash=token_hash(token), csrf_hash=token_hash(csrf), user_id=user.id,
                       expires_at=utcnow() + lifetime, idle_minutes=idle, ip=ctx.ip,
                       user_agent=(ctx.user_agent or "")[:256]))
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit.record(db, action="auth.login", category="AUTH", actor=user, entity="user", entity_id=user.id, ctx=ctx,
                 summary=f"Signed in with {method}", data={"remember_me": remember, "method": method})
    db.commit()
    return token, csrf


def resolve_session(db: Session, token: str | None) -> AuthSession | None:
    if not token or len(token) > 128:
        return None
    sess = db.execute(select(AuthSession).where(AuthSession.token_hash == token_hash(token))).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None:
        return None
    now = utcnow()
    if aware(sess.expires_at) <= now or aware(sess.last_seen_at) + timedelta(minutes=sess.idle_minutes) <= now:
        sess.revoked_at = now
        db.commit()
        return None
    if not sess.user.is_active:
        return None
    if (now - aware(sess.last_seen_at)).total_seconds() > 60:
        sess.last_seen_at = now
        db.commit()
    return sess


def revoke_user_sessions(db: Session, user_id: str, *, except_id: str | None = None) -> None:
    q = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_id:
        q = q.where(AuthSession.id != except_id)
    db.execute(q.values(revoked_at=utcnow()))
