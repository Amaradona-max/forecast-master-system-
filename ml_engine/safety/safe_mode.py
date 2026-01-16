from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ml_engine.config import artifact_dir, monitoring_dir, strict_calibrator_enabled


@dataclass(frozen=True)
class SafeModeState:
    enabled: bool
    reason: str | None


_CACHE: dict[str, Any] = {"loaded_at": 0.0, "ttl_s": 600.0, "by_champ": {}}


def _safe_mode_path(championship: str) -> Path:
    return monitoring_dir() / f"safe_mode_{championship}.json"


def _calibrator_exists(championship: str) -> bool:
    return (artifact_dir() / f"calibrator_1x2_{championship}.joblib").exists()


def get_safe_mode(championship: str) -> SafeModeState:
    now = time.time()
    ttl = float(_CACHE.get("ttl_s") or 600.0)
    if now - float(_CACHE.get("loaded_at") or 0.0) > ttl:
        _CACHE["loaded_at"] = now
        _CACHE["by_champ"] = {}

    by = _CACHE.get("by_champ")
    if isinstance(by, dict) and isinstance(by.get(championship), SafeModeState):
        return by[championship]

    if strict_calibrator_enabled() and not _calibrator_exists(championship):
        st = SafeModeState(enabled=True, reason="calibrator_missing")
        if isinstance(by, dict):
            by[championship] = st
        return st

    p = _safe_mode_path(championship)
    if not p.exists():
        st = SafeModeState(enabled=False, reason=None)
        if isinstance(by, dict):
            by[championship] = st
        return st

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        raw = None

    enabled = False
    reason = None
    if isinstance(raw, dict):
        enabled = bool(raw.get("safe_mode") or raw.get("enabled"))
        rr = raw.get("safe_mode_reason") or raw.get("reason")
        reason = str(rr) if rr is not None else None

    st = SafeModeState(enabled=enabled, reason=reason)
    if isinstance(by, dict):
        by[championship] = st
    return st

