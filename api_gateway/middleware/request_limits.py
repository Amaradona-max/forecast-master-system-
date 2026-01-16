from __future__ import annotations

import os
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ml_engine.resilience.timeouts import default_deadline_ms, reset_deadline, set_deadline_ms


def _max_body_bytes() -> int:
    try:
        v = int(str(os.getenv("FORECAST_MAX_JSON_BODY_BYTES", "131072") or "").strip())
    except Exception:
        v = 131072
    if v < 8192:
        v = 8192
    return v


def _is_json_content_type(request: Request) -> bool:
    ct = request.headers.get("content-type")
    if not isinstance(ct, str):
        return False
    ct = ct.split(";")[0].strip().lower()
    return ct == "application/json"


async def request_limits_middleware(request: Request, call_next: Any) -> Response:
    tok = set_deadline_ms(default_deadline_ms())
    path = str(getattr(request.url, "path", "") or "")
    method = str(getattr(request, "method", "") or "").upper()
    try:
        if path.startswith("/api/") and method in {"POST", "PUT", "PATCH"}:
            if not _is_json_content_type(request):
                return JSONResponse(status_code=415, content={"error": "unsupported_media_type"})

        if method in {"POST", "PUT", "PATCH"}:
            max_b = _max_body_bytes()
            cl = request.headers.get("content-length")
            try:
                n = int(cl) if isinstance(cl, str) else None
            except Exception:
                n = None
            if isinstance(n, int) and n > max_b:
                return JSONResponse(status_code=413, content={"error": "payload_too_large", "max_bytes": int(max_b)})
            body = await request.body()
            if len(body) > max_b:
                return JSONResponse(status_code=413, content={"error": "payload_too_large", "max_bytes": int(max_b)})
            request._body = body  # type: ignore[attr-defined]

        resp = await call_next(request)
        resp.headers["x-content-type-options"] = "nosniff"
        resp.headers["x-frame-options"] = "DENY"
        return resp
    finally:
        reset_deadline(tok)
