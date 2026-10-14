"""RFC 9457 problem+json errors. Internals are never leaked to clients (OWASP A10)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, detail: str, *, extra: dict[str, Any] | None = None):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra or {}


def not_found(entity: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{entity} not found.")


def forbidden(detail: str = "You do not have permission to perform this action.") -> AppError:
    return AppError(403, "forbidden", detail)


def conflict(detail: str, **extra: Any) -> AppError:
    return AppError(409, "conflict", detail, extra=extra)


def bad_request(detail: str, **extra: Any) -> AppError:
    return AppError(400, "bad_request", detail, extra=extra)


def _problem(request: Request, status: int, code: str, detail: str, extra: dict | None = None) -> JSONResponse:
    body = {
        "type": f"https://timetable.nfsu.ac.in/problems/{code}",
        "title": code.replace("_", " ").capitalize(),
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        resp = _problem(request, exc.status, exc.code, exc.detail, exc.extra)
        if exc.status == 429 and "retry_after_s" in exc.extra:
            resp.headers["Retry-After"] = str(exc.extra["retry_after_s"])
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return _problem(request, 422, "validation_error", "Some fields are invalid.", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
                413: "payload_too_large", 429: "rate_limited"}.get(exc.status_code, "http_error")
        return _problem(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error", extra={"path": request.url.path})
        return _problem(request, 500, "internal_error", "An unexpected error occurred. It has been logged.")
