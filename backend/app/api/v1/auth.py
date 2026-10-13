from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, request_ctx
from app.core.config import get_settings
from app.core.db import get_db, utcnow
from app.core.errors import AppError
from app.core.ratelimit import limiter
from app.core.roles import CREATABLE_ROLES, Role
from app.core.security import hash_password, password_problems, verify_password
from app.models.identity import User
from app.schemas.identity import LoginIn, MeOut, OtpRequestIn, OtpVerifyIn, PasswordChangeIn, PreferencesIn, ProfileIn
from app.services import audit
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

PERMISSIONS: dict[Role, list[str]] = {
    Role.ADMIN: ["*", "users.manage", "audit.read", "settings.system", "setup.write", "timetable.generate",
                 "timetable.publish", "requests.review"],
    Role.COORDINATOR: ["setup.write", "timetable.generate", "timetable.submit", "requests.review", "users.create"],
    Role.FACULTY: ["timetable.read", "availability.request", "session.request", "users.create"],
    Role.STUDENT: ["timetable.read"],
}


def _set_cookies(response: Response, token: str, csrf: str, remember: bool) -> None:
    s = get_settings()
    max_age = s.remember_me_days * 86400 if remember else None
    response.set_cookie(s.session_cookie, token, max_age=max_age, httponly=True, secure=s.cookie_secure,
                        samesite="strict", path="/api")
    response.set_cookie(s.csrf_cookie, csrf, max_age=max_age, httponly=False, secure=s.cookie_secure,
                        samesite="strict", path="/")


def _me(user: User, csrf: str | None = None) -> MeOut:
    out = MeOut.model_validate(user, from_attributes=True)
    out.permissions = PERMISSIONS[user.role] + [f"create:{r.value}" for r in CREATABLE_ROLES[user.role]]
    out.csrf_token = csrf
    return out


def _guard(request: Request, identifier: str) -> None:
    s = get_settings()
    ip = request_ctx(request).ip or "?"
    limiter.hit(f"login-ip:{ip}", s.login_rate_per_minute)
    limiter.hit(f"login-id:{identifier.strip().lower()}", s.login_rate_per_minute)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _guard(request, body.identifier)
    ctx = request_ctx(request)
    user = auth_service.authenticate(db, body.identifier, body.password, ctx)
    token, csrf = auth_service.start_session(db, user, remember=body.remember_me, ctx=ctx, method="password")
    _set_cookies(response, token, csrf, body.remember_me)
    return _me(user, csrf)


@router.post("/otp/request", status_code=202)
def otp_request(body: OtpRequestIn, request: Request, db: Session = Depends(get_db)):
    _guard(request, body.identifier)
    auth_service.request_otp(db, body.identifier, request_ctx(request))
    return {"detail": "If an account exists for this email, a sign-in code has been sent."}


@router.post("/otp/verify", response_model=MeOut)
def otp_verify(body: OtpVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _guard(request, body.identifier)
    ctx = request_ctx(request)
    user = auth_service.verify_otp(db, body.identifier, body.code, ctx)
    token, csrf = auth_service.start_session(db, user, remember=body.remember_me, ctx=ctx, method="email OTP")
    _set_cookies(response, token, csrf, body.remember_me)
    return _me(user, csrf)


@router.post("/logout", status_code=204)
def logout(response: Response, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    p.session.revoked_at = utcnow()
    audit.record(db, action="auth.logout", category="AUTH", actor=p.user, entity="user", entity_id=p.user.id,
                 ctx=p.ctx, summary="Signed out")
    db.commit()
    s = get_settings()
    response.delete_cookie(s.session_cookie, path="/api")
    response.delete_cookie(s.csrf_cookie, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(p: Principal = Depends(current_principal)):
    # The CSRF token is fixed for the session; the SPA reads it from the (non-HttpOnly) CSRF cookie,
    # so it survives page reloads and works across tabs.
    return _me(p.user)


@router.post("/password", status_code=204)
def change_password(body: PasswordChangeIn, request: Request, p: Principal = Depends(current_principal),
                    db: Session = Depends(get_db)):
    limiter.hit(f"pwchange:{p.user.id}", 5)
    if not verify_password(body.current_password, p.user.password_hash):
        audit.record(db, action="auth.password_change", category="SECURITY", actor=p.user, outcome="FAILURE",
                     entity="user", entity_id=p.user.id, ctx=p.ctx, summary="Password change failed: wrong current password")
        db.commit()
        raise AppError(400, "wrong_password", "Your current password is incorrect.")
    problems = password_problems(body.new_password, email=p.user.email, name=p.user.full_name)
    if body.new_password == body.current_password:
        problems.append("The new password must be different from the current one.")
    if problems:
        raise AppError(422, "weak_password", problems[0], extra={"errors": [{"field": "new_password", "message": m}
                                                                             for m in problems]})
    p.user.password_hash = hash_password(body.new_password)
    p.user.must_change_password = False
    p.user.password_changed_at = utcnow()
    auth_service.revoke_user_sessions(db, p.user.id, except_id=p.session.id)
    audit.record(db, action="auth.password_change", category="SECURITY", actor=p.user, entity="user",
                 entity_id=p.user.id, ctx=p.ctx, summary="Password changed; other sessions signed out")
    db.commit()
    return Response(status_code=204)


@router.put("/me/preferences", response_model=MeOut)
def set_preferences(body: PreferencesIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    p.user.preferences = body.model_dump()
    db.commit()
    return _me(p.user)


@router.patch("/me", response_model=MeOut)
def update_profile(body: ProfileIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    before = p.user.full_name
    p.user.full_name = body.full_name
    audit.record(db, action="user.profile_update", category="USER", actor=p.user, entity="user", entity_id=p.user.id,
                 ctx=p.ctx, summary="Updated own profile", data={"full_name": {"from": before, "to": body.full_name}})
    db.commit()
    return _me(p.user)
