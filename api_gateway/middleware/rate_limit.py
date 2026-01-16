from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass
class _Bucket:
    capacity: float
    tokens: float
    refill_per_sec: float
    updated_at: float


def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, str(default)) or "").strip())
    except Exception:
        v = default
    return v if v > 0 else default


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if isinstance(xff, str) and xff.strip():
        ip0 = xff.split(",")[0].strip()
        if ip0:
            return ip0
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host or "unknown")


def _route_group(path: str) -> str:
    p = str(path or "")
    if p.startswith("/api/v1/predictions"):
        return "predictions"
    if p.startswith("/api/v1/quality") or p.startswith("/api/v1/accuracy"):
        return "quality"
    if p.startswith("/api/v1/metrics"):
        return "metrics"
    return "global"


class RateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._buckets: dict[str, _Bucket] = {}

    def _rate_per_minute(self, group: str) -> int:
        if group == "predictions":
            return _env_int("FORECAST_RL_PREDICTIONS_PER_MIN", 60)
        if group == "quality":
            return _env_int("FORECAST_RL_QUALITY_PER_MIN", 30)
        if group == "metrics":
            return _env_int("FORECAST_RL_METRICS_PER_MIN", 10)
        return _env_int("FORECAST_RL_GLOBAL_PER_MIN", 120)

    def _take(self, *, key: str, rate_per_min: int, now: float) -> tuple[bool, int]:
        cap = float(rate_per_min)
        refill_per_sec = cap / 60.0
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(capacity=cap, tokens=cap, refill_per_sec=refill_per_sec, updated_at=now)
            self._buckets[key] = b
        dt = max(0.0, float(now) - float(b.updated_at))
        b.tokens = min(b.capacity, float(b.tokens) + dt * b.refill_per_sec)
        b.updated_at = now
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True, 0
        missing = 1.0 - float(b.tokens)
        retry = int(max(1.0, missing / b.refill_per_sec)) if b.refill_per_sec > 0 else 60
        return False, retry

    def allow(self, *, ip: str, path: str, now: float | None = None) -> tuple[bool, int]:
        n = float(now) if isinstance(now, (int, float)) else time.time()
        group = _route_group(path)
        with self._lock:
            ok_g, retry_g = self._take(key=f"ip|{ip}", rate_per_min=self._rate_per_minute("global"), now=n)
            if not ok_g:
                return False, retry_g
            ok_r, retry_r = self._take(key=f"ip|{ip}|{group}", rate_per_min=self._rate_per_minute(group), now=n)
            if not ok_r:
                return False, retry_r
        return True, 0


_RL = RateLimiter()


async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
    path = str(getattr(request.url, "path", "") or "")
    if path in {"/docs", "/openapi.json", "/redoc"}:
        return await call_next(request)
    ip = _client_ip(request)
    ok, retry = _RL.allow(ip=ip, path=path)
    if not ok:
        return JSONResponse(
            status_code=429,
            headers={"retry-after": str(int(retry))},
            content={"error": "rate_limited", "retry_after_seconds": int(retry)},
        )
    return await call_next(request)

