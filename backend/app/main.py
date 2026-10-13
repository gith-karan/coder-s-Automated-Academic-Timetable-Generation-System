from __future__ import annotations

import logging
import logging.handlers
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import auth, people, resources, setup, timetables
from app.core.config import get_settings
from app.core.db import Base, engine
from app.core.errors import install_error_handlers
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.models.audit import install_audit_guards


def _configure_logging() -> None:
    s = get_settings()
    os.makedirs(s.log_dir, exist_ok=True)
    root = logging.getLogger("app")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(console)
    access = logging.handlers.RotatingFileHandler(os.path.join(s.log_dir, "access.jsonl"), maxBytes=10_000_000,
                                                  backupCount=10, encoding="utf-8")
    access.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("app.access").addHandler(access)


def init_db() -> None:
    import app.models  # noqa: F401 - register models

    Base.metadata.create_all(engine)
    install_audit_guards(engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _configure_logging()
    init_db()
    from app.bootstrap import ensure_admin

    ensure_admin()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description="Automated academic timetable generation for National Forensic Sciences University.",
        lifespan=lifespan,
        docs_url=None if s.is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if s.is_prod else "/api/v1/openapi.json",
    )
    install_error_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.trusted_hosts)

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth.router)
    v1.include_router(people.router)
    v1.include_router(resources.router)
    v1.include_router(setup.router)
    v1.include_router(timetables.router)
    v1.include_router(timetables.runs)
    v1.include_router(timetables.requests_router)
    if not s.is_prod:
        from app.api.v1 import demo

        v1.include_router(demo.router)
    app.include_router(v1)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()
