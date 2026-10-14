"""Application settings, loaded from environment variables / .env.

Production refuses to start with insecure defaults (OWASP A02).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-secret-change-me-dev-only-secret-change-me"
_DEV_AUDIT_KEY = "dev-only-audit-key-change-me-dev-only-audit-key-change"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NFSU_", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    app_name: str = "NFSU Timetable System"
    database_url: str = "sqlite:///./data/app.db"

    # Secrets. In prod these MUST be supplied via environment / secret store.
    secret_key: str = _DEV_SECRET
    audit_hmac_key: str = _DEV_AUDIT_KEY

    # Sessions (server-side, cookie carries an opaque random token only)
    session_cookie: str = "nfsu_session"
    csrf_cookie: str = "nfsu_csrf"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    remember_me_days: int = 7
    cookie_secure: bool = False  # forced True in prod

    # Brute-force protection
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    login_rate_per_minute: int = 10
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    max_body_bytes: int = 2 * 1024 * 1024

    # Solver guard rails (OWASP A06: solver must not become a DoS vector)
    solver_time_limit_s: int = 30
    solver_max_time_limit_s: int = 300  # upper bound for the admin-set safety cap
    solver_workers: int = 8
    max_concurrent_runs: int = 2

    bootstrap_admin_email: str = "admin@nfsu.ac.in"
    bootstrap_admin_password: str | None = None  # if None, a random one is printed once
    demo_password: str | None = None  # dev only: password for seeded demo users

    mail_backend: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "timetable-noreply@nfsu.ac.in"

    log_dir: str = "./data/logs"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @model_validator(mode="after")
    def _harden(self) -> "Settings":
        if self.env == "prod":
            if self.secret_key == _DEV_SECRET or len(self.secret_key) < 32:
                raise ValueError("NFSU_SECRET_KEY must be set to a strong (>=32 chars) value in prod")
            if self.audit_hmac_key == _DEV_AUDIT_KEY or len(self.audit_hmac_key) < 32:
                raise ValueError("NFSU_AUDIT_HMAC_KEY must be set to a strong (>=32 chars) value in prod")
            if self.database_url.startswith("sqlite"):
                raise ValueError("SQLite is not allowed in prod; use PostgreSQL")
            self.cookie_secure = True
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
