from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, TypeVar


T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitSnapshot:
    state: str
    failures: int
    opened_at: float | None
    half_open_calls: int


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 5, recovery_timeout_sec: int = 30, half_open_max_calls: int = 3) -> None:
        self._failure_threshold = int(failure_threshold)
        self._recovery_timeout_sec = int(recovery_timeout_sec)
        self._half_open_max_calls = int(half_open_max_calls)
        self._lock = Lock()
        self._state = "CLOSED"
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_calls = 0

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            return CircuitSnapshot(
                state=str(self._state),
                failures=int(self._failures),
                opened_at=float(self._opened_at) if isinstance(self._opened_at, (int, float)) else None,
                half_open_calls=int(self._half_open_calls),
            )

    def _transition_if_needed(self, now: float) -> None:
        if self._state == "OPEN":
            opened_at = float(self._opened_at or 0.0)
            if (now - opened_at) >= float(self._recovery_timeout_sec):
                self._state = "HALF_OPEN"
                self._half_open_calls = 0

    def _allow_call(self, now: float) -> None:
        self._transition_if_needed(now)
        if self._state == "OPEN":
            raise CircuitOpenError("circuit_open")
        if self._state == "HALF_OPEN":
            if self._half_open_calls >= self._half_open_max_calls:
                raise CircuitOpenError("circuit_half_open_limit")
            self._half_open_calls += 1

    def _on_success(self) -> None:
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            self._failures = 0
            self._opened_at = None
            self._half_open_calls = 0
            return
        self._failures = 0

    def _on_failure(self, now: float) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._state = "OPEN"
            self._opened_at = float(now)
            self._half_open_calls = 0

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        now = time.time()
        with self._lock:
            self._allow_call(now)
        try:
            out = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._on_failure(now)
            raise
        with self._lock:
            self._on_success()
        return out


_REGISTRY_LOCK = Lock()
_REGISTRY: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    k = str(name or "").strip() or "default"
    with _REGISTRY_LOCK:
        b = _REGISTRY.get(k)
        if b is None:
            b = CircuitBreaker()
            _REGISTRY[k] = b
        return b

