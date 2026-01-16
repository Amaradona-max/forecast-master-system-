from __future__ import annotations

import contextvars
import os
import time


_deadline_at: contextvars.ContextVar[float | None] = contextvars.ContextVar("deadline_at_monotonic", default=None)


def default_deadline_ms() -> int:
    try:
        v = int(str(os.getenv("FORECAST_REQUEST_DEADLINE_MS", "900") or "").strip())
    except Exception:
        v = 900
    if v < 100:
        v = 100
    if v > 10_000:
        v = 10_000
    return v


def set_deadline_ms(ms: int) -> contextvars.Token:
    d_ms = int(ms)
    if d_ms <= 0:
        return _deadline_at.set(None)
    deadline = time.monotonic() + (float(d_ms) / 1000.0)
    return _deadline_at.set(deadline)


def reset_deadline(token: contextvars.Token) -> None:
    _deadline_at.reset(token)


def deadline_at_monotonic() -> float | None:
    v = _deadline_at.get()
    return float(v) if isinstance(v, (int, float)) else None


def time_left_ms() -> int | None:
    d = deadline_at_monotonic()
    if d is None:
        return None
    left = (float(d) - time.monotonic()) * 1000.0
    return int(left) if left > 0 else 0

