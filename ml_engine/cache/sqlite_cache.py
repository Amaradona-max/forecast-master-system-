from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml_engine.resilience.circuit_breaker import CircuitOpenError, get_breaker
from ml_engine.config import sqlite_busy_timeout_ms


@dataclass(frozen=True)
class CacheHit:
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    model_version: str | None
    feature_version: str | None
    calibrator_version: str | None
    inputs_hash: str | None


class SqliteCache:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=3.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute(f"PRAGMA busy_timeout={int(sqlite_busy_timeout_ms())};")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS predictions_cache (
                    cache_key TEXT PRIMARY KEY,
                    championship TEXT,
                    match_id TEXT,
                    matchday INTEGER,
                    payload_json TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    model_version TEXT,
                    feature_version TEXT,
                    calibrator_version TEXT,
                    inputs_hash TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_champ_md ON predictions_cache(championship, matchday)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_expires ON predictions_cache(expires_at)")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics_runtime (
                    day TEXT,
                    route TEXT,
                    count INTEGER,
                    err_count INTEGER,
                    latency_ms_sum REAL,
                    latency_ms_p50 REAL,
                    latency_ms_p95 REAL,
                    cache_hits INTEGER,
                    cache_misses INTEGER,
                    PRIMARY KEY (day, route)
                )
                """
            )

    def quick_check(self) -> bool:
        try:
            return bool(get_breaker("sqlite_cache").call(self._quick_check_impl))
        except CircuitOpenError:
            return False

    def _quick_check_impl(self) -> bool:
        with self._connect() as conn:
            cur = conn.execute("PRAGMA quick_check;")
            row = cur.fetchone()
            return bool(row and str(row[0]).strip().lower() == "ok")

    def vacuum(self) -> None:
        try:
            get_breaker("sqlite_cache").call(self._vacuum_impl)
        except CircuitOpenError:
            return

    def _vacuum_impl(self) -> None:
        with self._connect() as conn:
            conn.execute("VACUUM;")

    def analyze(self) -> None:
        try:
            get_breaker("sqlite_cache").call(self._analyze_impl)
        except CircuitOpenError:
            return

    def _analyze_impl(self) -> None:
        with self._connect() as conn:
            conn.execute("ANALYZE;")

    def get(self, *, cache_key: str, now_utc: datetime | None = None) -> CacheHit | None:
        now = now_utc or datetime.now(timezone.utc)
        try:
            return get_breaker("sqlite_cache").call(self._get_impl, cache_key=str(cache_key), now=now)
        except CircuitOpenError:
            return None

    def _get_impl(self, *, cache_key: str, now: datetime) -> CacheHit | None:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT payload_json, created_at, expires_at, model_version, feature_version, calibrator_version, inputs_hash
                FROM predictions_cache
                WHERE cache_key = ?
                """,
                (str(cache_key),),
            )
            row = cur.fetchone()
            if not row:
                return None
            payload_json, created_at, expires_at, model_version, feature_version, calibrator_version, inputs_hash = row
            try:
                exp_dt = datetime.fromisoformat(str(expires_at))
            except Exception:
                exp_dt = datetime.fromtimestamp(0, tz=timezone.utc)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt <= now:
                conn.execute("DELETE FROM predictions_cache WHERE cache_key = ?", (str(cache_key),))
                return None

            try:
                c_dt = datetime.fromisoformat(str(created_at))
            except Exception:
                c_dt = now
            if c_dt.tzinfo is None:
                c_dt = c_dt.replace(tzinfo=timezone.utc)

            try:
                payload = json.loads(str(payload_json or "") or "{}")
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            return CacheHit(
                payload=payload,
                created_at=c_dt,
                expires_at=exp_dt,
                model_version=str(model_version) if model_version is not None else None,
                feature_version=str(feature_version) if feature_version is not None else None,
                calibrator_version=str(calibrator_version) if calibrator_version is not None else None,
                inputs_hash=str(inputs_hash) if inputs_hash is not None else None,
            )

    def set(
        self,
        *,
        cache_key: str,
        championship: str,
        match_id: str,
        matchday: int | None,
        payload: dict[str, Any],
        ttl_seconds: int,
        model_version: str,
        feature_version: str,
        calibrator_version: str,
        inputs_hash: str,
        now_utc: datetime | None = None,
    ) -> None:
        now = now_utc or datetime.now(timezone.utc)
        try:
            get_breaker("sqlite_cache").call(
                self._set_impl,
                cache_key=str(cache_key),
                championship=str(championship),
                match_id=str(match_id),
                matchday=int(matchday) if isinstance(matchday, int) else None,
                payload=dict(payload),
                ttl_seconds=int(ttl_seconds),
                model_version=str(model_version),
                feature_version=str(feature_version),
                calibrator_version=str(calibrator_version),
                inputs_hash=str(inputs_hash),
                now=now,
            )
        except CircuitOpenError:
            return

    def _set_impl(
        self,
        *,
        cache_key: str,
        championship: str,
        match_id: str,
        matchday: int | None,
        payload: dict[str, Any],
        ttl_seconds: int,
        model_version: str,
        feature_version: str,
        calibrator_version: str,
        inputs_hash: str,
        now: datetime,
    ) -> None:
        ttl = int(ttl_seconds)
        if ttl <= 0:
            return
        expires_at = now.timestamp() + float(ttl)
        exp_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO predictions_cache (
                    cache_key, championship, match_id, matchday, payload_json, created_at, expires_at,
                    model_version, feature_version, calibrator_version, inputs_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(cache_key),
                    str(championship),
                    str(match_id),
                    int(matchday) if isinstance(matchday, int) else None,
                    str(raw),
                    now.isoformat(),
                    exp_dt.isoformat(),
                    str(model_version),
                    str(feature_version),
                    str(calibrator_version),
                    str(inputs_hash),
                ),
            )

    def incr_runtime_metrics(
        self,
        *,
        day: str,
        route: str,
        latency_ms: float,
        is_error: bool,
        cache_hits: int = 0,
        cache_misses: int = 0,
    ) -> None:
        d = str(day)
        r = str(route)
        lat = float(latency_ms)
        err = 1 if bool(is_error) else 0
        hits = int(cache_hits)
        misses = int(cache_misses)
        if hits < 0:
            hits = 0
        if misses < 0:
            misses = 0
        if lat < 0:
            lat = 0.0
        try:
            get_breaker("sqlite_cache").call(
                self._incr_runtime_metrics_impl,
                day=d,
                route=r,
                latency_ms=float(lat),
                err=int(err),
                hits=int(hits),
                misses=int(misses),
            )
        except CircuitOpenError:
            return

    def _incr_runtime_metrics_impl(self, *, day: str, route: str, latency_ms: float, err: int, hits: int, misses: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO metrics_runtime (
                    day, route, count, err_count, latency_ms_sum, latency_ms_p50, latency_ms_p95, cache_hits, cache_misses
                ) VALUES (?, ?, 0, 0, 0.0, NULL, NULL, 0, 0)
                """,
                (str(day), str(route)),
            )
            conn.execute(
                """
                UPDATE metrics_runtime
                SET
                    count = count + 1,
                    err_count = err_count + ?,
                    latency_ms_sum = latency_ms_sum + ?,
                    cache_hits = cache_hits + ?,
                    cache_misses = cache_misses + ?
                WHERE day = ? AND route = ?
                """,
                (int(err), float(latency_ms), int(hits), int(misses), str(day), str(route)),
            )

    def delete_expired(self, *, now_utc: datetime | None = None) -> int:
        now = now_utc or datetime.now(timezone.utc)
        try:
            return int(get_breaker("sqlite_cache").call(self._delete_expired_impl, now_iso=now.isoformat()))
        except CircuitOpenError:
            return 0

    def _delete_expired_impl(self, *, now_iso: str) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM predictions_cache WHERE expires_at <= ?", (str(now_iso),))
            return int(cur.rowcount or 0)


def recover_corrupt_sqlite_db(*, db_path: Path) -> bool:
    p = Path(db_path)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    moved_any = False
    for suf in ["", "-wal", "-shm"]:
        fp = Path(str(p) + suf)
        if fp.exists():
            try:
                fp.rename(Path(str(fp) + f".bak.{ts}"))
                moved_any = True
            except Exception:
                pass
    try:
        SqliteCache(db_path=p)
        return True
    except Exception:
        return moved_any
