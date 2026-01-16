from __future__ import annotations

import os
from pathlib import Path


def artifact_dir() -> Path:
    return Path(os.getenv("ARTIFACT_DIR", "data/models")).resolve()


def data_dir() -> Path:
    return Path(os.getenv("FORECAST_DATA_DIR", "data")).resolve()


def cache_db_path() -> Path:
    return Path(os.getenv("FORECAST_CACHE_DB", str(data_dir() / "cache.sqlite"))).resolve()


def monitoring_dir() -> Path:
    return Path(os.getenv("FORECAST_MONITORING_DIR", str(data_dir() / "monitoring"))).resolve()


def monitoring_rotate_max_bytes() -> int:
    try:
        v = int(str(os.getenv("FORECAST_MONITORING_ROTATE_MAX_BYTES", str(50 * 1024 * 1024)) or "").strip())
    except Exception:
        v = 50 * 1024 * 1024
    if v < 1024 * 1024:
        v = 1024 * 1024
    if v > 1024 * 1024 * 1024:
        v = 1024 * 1024 * 1024
    return v


def monitoring_retain_days_uncompressed() -> int:
    try:
        v = int(str(os.getenv("FORECAST_MONITORING_RETAIN_DAYS_UNCOMPRESSED", "30") or "").strip())
    except Exception:
        v = 30
    if v < 1:
        v = 1
    if v > 365:
        v = 365
    return v


def monitoring_retain_days_compressed() -> int:
    try:
        v = int(str(os.getenv("FORECAST_MONITORING_RETAIN_DAYS_COMPRESSED", "180") or "").strip())
    except Exception:
        v = 180
    if v < 7:
        v = 7
    if v > 3650:
        v = 3650
    return v


def sqlite_busy_timeout_ms() -> int:
    try:
        v = int(str(os.getenv("FORECAST_SQLITE_BUSY_TIMEOUT_MS", "1000") or "").strip())
    except Exception:
        v = 1000
    if v < 100:
        v = 100
    if v > 10_000:
        v = 10_000
    return v


def strict_calibrator_enabled() -> bool:
    v = str(os.getenv("STRICT_CALIBRATOR", "0") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}
