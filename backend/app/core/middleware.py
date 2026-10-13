"""HTTP hardening: security headers, request IDs, structured access log, body size limit."""
from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

access_log = logging.getLogger("app.access")

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # Tailwind/Radix inline style attributes
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("Content-Security-Policy", _CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        if get_settings().is_prod:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, enforces body size limit, writes one JSON access-log line per request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID", "")
        if not (0 < len(rid) <= 64 and rid.replace("-", "").isalnum()):
            rid = uuid.uuid4().hex
        request.state.request_id = rid

        limit = get_settings().max_body_bytes
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            return JSONResponse(
                {"status": 413, "code": "payload_too_large", "detail": "Request body too large."},
                status_code=413, media_type="application/problem+json",
            )

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = rid
        access_log.info(json.dumps({
            "rid": rid, "method": request.method, "path": request.url.path, "status": response.status_code,
            "ms": elapsed_ms, "ip": client_ip(request), "uid": getattr(request.state, "user_id", None),
        }))
        return response


def client_ip(request: Request) -> str:
    # Behind Caddy we trust exactly one proxy hop; uvicorn --proxy-headers sets request.client.
    return request.client.host if request.client else "unknown"
