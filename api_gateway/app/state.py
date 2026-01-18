from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api_gateway.app.settings import settings


@dataclass
class LiveMatchState:
    match_id: str
    championship: str
    home_team: str
    away_team: str
    status: str = "PREMATCH"
    matchday: int | None = None
    kickoff_unix: float | None = None
    next_update_unix: float | None = None
    updated_at_unix: float = field(default_factory=lambda: time.time())
    probabilities: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def update(
        self,
        *,
        status: str | None = None,
        matchday: int | None = None,
        kickoff_unix: float | None = None,
        next_update_unix: float | None = None,
        probabilities: dict[str, float] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if status is not None:
            self.status = status
        if matchday is not None:
            self.matchday = matchday
        if kickoff_unix is not None:
            self.kickoff_unix = kickoff_unix
        if next_update_unix is not None:
            self.next_update_unix = next_update_unix
        if probabilities is not None:
            self.probabilities = probabilities
        if meta is not None:
            self.meta = meta
        self.updated_at_unix = time.time()


class AppState:
    def __init__(self) -> None:
        self.matches: dict[str, LiveMatchState] = {}
        self._lock = asyncio.Lock()
        self._db_path = str(getattr(settings, "state_db_path", "data/forecast_state.sqlite3") or "data/forecast_state.sqlite3")
        self._db_enabled = False
        self._calibration_cache: dict[str, tuple[float, float]] = {}
        self._calibration_dirty = True
        self._init_db()
        self._load_from_db()

    def _init_db(self) -> None:
        p = Path(self._db_path)
        try:
            if p.parent:
                p.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._db_path, timeout=5) as con:
                con.execute("PRAGMA journal_mode=WAL;")
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS matches (
                        match_id TEXT PRIMARY KEY,
                        championship TEXT NOT NULL,
                        home_team TEXT NOT NULL,
                        away_team TEXT NOT NULL,
                        status TEXT NOT NULL,
                        matchday INTEGER,
                        kickoff_unix REAL,
                        next_update_unix REAL,
                        updated_at_unix REAL NOT NULL,
                        probabilities_json TEXT NOT NULL,
                        meta_json TEXT NOT NULL,
                        final_home_goals INTEGER,
                        final_away_goals INTEGER
                    );
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_cache (
                        cache_key TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        fetched_at_unix REAL NOT NULL,
                        ttl_seconds REAL NOT NULL
                    );
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS match_odds (
                        match_id TEXT NOT NULL,
                        market TEXT NOT NULL,
                        odds REAL NOT NULL,
                        source TEXT,
                        updated_at_unix REAL NOT NULL,
                        PRIMARY KEY (match_id, market)
                    );
                    """
                )
                con.execute("CREATE INDEX IF NOT EXISTS idx_match_odds_updated ON match_odds(updated_at_unix DESC);")
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notifications_outbox (
                        notification_id TEXT PRIMARY KEY,
                        notification_key TEXT UNIQUE,
                        type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at_unix REAL NOT NULL,
                        sent_email INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
                con.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications_outbox(created_at_unix DESC);")
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notification_preferences (
                        user_id TEXT PRIMARY KEY,
                        enabled INTEGER NOT NULL,
                        channels_json TEXT NOT NULL,
                        quiet_hours_json TEXT NOT NULL,
                        max_per_day INTEGER NOT NULL,
                        min_interval_minutes INTEGER NOT NULL,
                        updated_at_unix REAL NOT NULL
                    );
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_config (
                        tenant_id TEXT PRIMARY KEY,
                        config_json TEXT NOT NULL,
                        updated_at_unix REAL NOT NULL
                    );
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notifications_delivery_log (
                        user_id TEXT NOT NULL,
                        channel TEXT NOT NULL,
                        notification_key TEXT NOT NULL,
                        type TEXT NOT NULL,
                        sent_at_unix REAL NOT NULL,
                        day_utc TEXT NOT NULL,
                        PRIMARY KEY (user_id, channel, notification_key)
                    );
                    """
                )
                con.execute("CREATE INDEX IF NOT EXISTS idx_delivery_log_day ON notifications_delivery_log(day_utc);")
                con.execute("CREATE INDEX IF NOT EXISTS idx_delivery_log_user_time ON notifications_delivery_log(user_id, sent_at_unix DESC);")
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS predictions_history (
                        prediction_id TEXT PRIMARY KEY,
                        match_id TEXT NOT NULL,
                        championship TEXT NOT NULL,
                        home_team TEXT NOT NULL,
                        away_team TEXT NOT NULL,
                        market TEXT NOT NULL,
                        predicted_pick TEXT NOT NULL,
                        predicted_prob REAL NOT NULL,
                        confidence REAL NOT NULL,
                        predicted_at_unix REAL NOT NULL,
                        kickoff_unix REAL,
                        final_outcome TEXT,
                        final_home_goals INTEGER,
                        final_away_goals INTEGER,
                        correct INTEGER,
                        roi_simulated REAL,
                        resolved_at_unix REAL,
                        UNIQUE (match_id, market)
                    );
                    """
                )
                con.execute("CREATE INDEX IF NOT EXISTS idx_predictions_championship ON predictions_history(championship);")
                con.execute("CREATE INDEX IF NOT EXISTS idx_predictions_predicted_at ON predictions_history(predicted_at_unix DESC);")
                con.execute("CREATE INDEX IF NOT EXISTS idx_predictions_resolved_at ON predictions_history(resolved_at_unix DESC);")
                con.execute("CREATE INDEX IF NOT EXISTS idx_matches_championship ON matches(championship);")
                con.execute("CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);")
                con.execute("CREATE INDEX IF NOT EXISTS idx_matches_kickoff_unix ON matches(kickoff_unix);")
            self._db_enabled = True
        except Exception:
            self._db_enabled = False

    def _load_from_db(self) -> None:
        if not self._db_enabled:
            return
        try:
            with sqlite3.connect(self._db_path, timeout=5) as con:
                rows = con.execute(
                    """
                    SELECT
                        match_id,
                        championship,
                        home_team,
                        away_team,
                        status,
                        matchday,
                        kickoff_unix,
                        next_update_unix,
                        updated_at_unix,
                        probabilities_json,
                        meta_json
                    FROM matches;
                    """
                ).fetchall()
        except Exception:
            return

        for r in rows:
            try:
                probs = json.loads(r[9]) if isinstance(r[9], str) else {}
            except Exception:
                probs = {}
            try:
                meta = json.loads(r[10]) if isinstance(r[10], str) else {}
            except Exception:
                meta = {}
            if bool(getattr(settings, "real_data_only", False)):
                ctx = meta.get("context") if isinstance(meta, dict) else None
                if not isinstance(ctx, dict):
                    continue
                src = ctx.get("source") if isinstance(ctx.get("source"), dict) else None
                if not isinstance(src, dict):
                    continue
                if str(src.get("provider") or "").strip() != "football_data":
                    continue
            m = LiveMatchState(
                match_id=str(r[0]),
                championship=str(r[1]),
                home_team=str(r[2]),
                away_team=str(r[3]),
                status=str(r[4]),
                matchday=int(r[5]) if isinstance(r[5], int) else None,
                kickoff_unix=float(r[6]) if isinstance(r[6], (int, float)) else None,
                next_update_unix=float(r[7]) if isinstance(r[7], (int, float)) else None,
                updated_at_unix=float(r[8]) if isinstance(r[8], (int, float)) else time.time(),
                probabilities={str(k): float(v) for k, v in (probs.items() if isinstance(probs, dict) else []) if isinstance(v, (int, float))},
                meta=meta if isinstance(meta, dict) else {},
            )
            self.matches[m.match_id] = m

        self._reconcile_unresolved_predictions_from_finished_matches()

    def _reconcile_unresolved_predictions_from_finished_matches(self) -> None:
        if not self._db_enabled:
            return
        try:
            with sqlite3.connect(self._db_path, timeout=5) as con:
                rows = con.execute(
                    """
                    SELECT match_id, final_home_goals, final_away_goals, updated_at_unix
                    FROM matches
                    WHERE status='FINISHED'
                      AND final_home_goals IS NOT NULL
                      AND final_away_goals IS NOT NULL;
                    """
                ).fetchall()
        except Exception:
            return
        now_unix = float(time.time())
        for r in rows:
            if not isinstance(r, tuple) or len(r) < 4:
                continue
            match_id, hg, ag, updated_at_unix = r[:4]
            if not isinstance(match_id, str) or not match_id.strip():
                continue
            if not isinstance(hg, int) or not isinstance(ag, int):
                continue
            resolved_at = float(updated_at_unix) if isinstance(updated_at_unix, (int, float)) else now_unix
            outc = self._outcome_from_score(int(hg), int(ag))
            try:
                self._db_resolve_predictions_for_match(
                    match_id=str(match_id),
                    final_outcome=str(outc),
                    final_home_goals=int(hg),
                    final_away_goals=int(ag),
                    resolved_at_unix=float(resolved_at),
                )
            except Exception:
                continue

    def _extract_final_score(self, match: LiveMatchState) -> tuple[int, int] | None:
        meta = match.meta if isinstance(match.meta, dict) else {}
        ctx = meta.get("context") if isinstance(meta.get("context"), dict) else None
        if not isinstance(ctx, dict):
            return None
        fs = ctx.get("final_score")
        if not isinstance(fs, dict):
            return None
        hg = fs.get("home")
        ag = fs.get("away")
        if not isinstance(hg, int) or not isinstance(ag, int):
            return None
        return (int(hg), int(ag))

    def _outcome_from_score(self, hg: int, ag: int) -> str:
        if int(hg) > int(ag):
            return "home_win"
        if int(hg) == int(ag):
            return "draw"
        return "away_win"

    def _db_upsert_match(self, row: dict[str, Any]) -> None:
        if not self._db_enabled:
            return
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT INTO matches (
                    match_id,
                    championship,
                    home_team,
                    away_team,
                    status,
                    matchday,
                    kickoff_unix,
                    next_update_unix,
                    updated_at_unix,
                    probabilities_json,
                    meta_json,
                    final_home_goals,
                    final_away_goals
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    championship=excluded.championship,
                    home_team=excluded.home_team,
                    away_team=excluded.away_team,
                    status=excluded.status,
                    matchday=excluded.matchday,
                    kickoff_unix=excluded.kickoff_unix,
                    next_update_unix=excluded.next_update_unix,
                    updated_at_unix=excluded.updated_at_unix,
                    probabilities_json=excluded.probabilities_json,
                    meta_json=excluded.meta_json,
                    final_home_goals=excluded.final_home_goals,
                    final_away_goals=excluded.final_away_goals;
                """,
                (
                    row["match_id"],
                    row["championship"],
                    row["home_team"],
                    row["away_team"],
                    row["status"],
                    row["matchday"],
                    row["kickoff_unix"],
                    row["next_update_unix"],
                    row["updated_at_unix"],
                    row["probabilities_json"],
                    row["meta_json"],
                    row["final_home_goals"],
                    row["final_away_goals"],
                ),
            )

    def _db_clear_all(self) -> None:
        if not self._db_enabled:
            return
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute("DELETE FROM matches;")

    def _db_get_cache(self, cache_key: str, now_unix: float) -> str | None:
        if not self._db_enabled:
            return None
        k = str(cache_key or "").strip()
        if not k:
            return None
        with sqlite3.connect(self._db_path, timeout=5) as con:
            row = con.execute(
                """
                SELECT payload_json, fetched_at_unix, ttl_seconds
                FROM api_cache
                WHERE cache_key=?;
                """,
                (k,),
            ).fetchone()
            if not isinstance(row, tuple) or len(row) < 3:
                return None
            payload_json, fetched_at_unix, ttl_seconds = row[0], row[1], row[2]
            try:
                fetched = float(fetched_at_unix)
                ttl = float(ttl_seconds)
            except Exception:
                con.execute("DELETE FROM api_cache WHERE cache_key=?;", (k,))
                return None
            if ttl <= 0 or (float(now_unix) - fetched) > ttl:
                con.execute("DELETE FROM api_cache WHERE cache_key=?;", (k,))
                return None
            return str(payload_json) if isinstance(payload_json, str) else None

    def _db_set_cache(self, cache_key: str, payload_json: str, fetched_at_unix: float, ttl_seconds: float) -> None:
        if not self._db_enabled:
            return
        k = str(cache_key or "").strip()
        if not k:
            return
        try:
            fetched = float(fetched_at_unix)
            ttl = float(ttl_seconds)
        except Exception:
            return
        if ttl <= 0:
            return
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT INTO api_cache (cache_key, payload_json, fetched_at_unix, ttl_seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    fetched_at_unix=excluded.fetched_at_unix,
                    ttl_seconds=excluded.ttl_seconds;
                """,
                (k, str(payload_json), fetched, ttl),
            )

    def _db_upsert_odds(self, *, match_id: str, market: str, odds: float, source: str | None, now_unix: float) -> None:
        if not self._db_enabled:
            return
        mid = str(match_id or "").strip()
        mk = str(market or "").strip().upper()
        if not mid or not mk:
            return
        o = float(odds)
        if o <= 1.01:
            return
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT INTO match_odds (match_id, market, odds, source, updated_at_unix)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(match_id, market) DO UPDATE SET
                    odds=excluded.odds,
                    source=excluded.source,
                    updated_at_unix=excluded.updated_at_unix;
                """,
                (mid, mk, float(o), str(source or "") or None, float(now_unix)),
            )

    def _db_list_odds(self, *, limit: int) -> list[tuple[str, str, float, str | None, float]]:
        if not self._db_enabled:
            return []
        lim = int(limit)
        if lim <= 0:
            lim = 50
        if lim > 500:
            lim = 500
        with sqlite3.connect(self._db_path, timeout=5) as con:
            rows = con.execute(
                """
                SELECT match_id, market, odds, source, updated_at_unix
                FROM match_odds
                ORDER BY updated_at_unix DESC
                LIMIT ?;
                """,
                (int(lim),),
            ).fetchall()
        out: list[tuple[str, str, float, str | None, float]] = []
        for r in rows:
            if not isinstance(r, tuple) or len(r) < 5:
                continue
            try:
                out.append((str(r[0]), str(r[1]), float(r[2]), (str(r[3]) if r[3] is not None else None), float(r[4])))
            except Exception:
                continue
        return out

    def _db_upsert_prediction_history(
        self,
        *,
        prediction_id: str,
        match_id: str,
        championship: str,
        home_team: str,
        away_team: str,
        market: str,
        predicted_pick: str,
        predicted_prob: float,
        confidence: float,
        predicted_at_unix: float,
        kickoff_unix: float | None,
    ) -> None:
        if not self._db_enabled:
            return
        pid = str(prediction_id or "").strip()
        mid = str(match_id or "").strip()
        champ = str(championship or "").strip()
        mk = str(market or "").strip().upper()
        pick = str(predicted_pick or "").strip()
        if not pid or not mid or not champ or not mk or not pick:
            return
        prob = float(predicted_prob)
        if prob < 0.0:
            prob = 0.0
        if prob > 1.0:
            prob = 1.0
        conf = float(confidence)
        if conf < 0.0:
            conf = 0.0
        if conf > 1.0:
            conf = 1.0
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT INTO predictions_history (
                    prediction_id,
                    match_id,
                    championship,
                    home_team,
                    away_team,
                    market,
                    predicted_pick,
                    predicted_prob,
                    confidence,
                    predicted_at_unix,
                    kickoff_unix,
                    final_outcome,
                    final_home_goals,
                    final_away_goals,
                    correct,
                    roi_simulated,
                    resolved_at_unix
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL)
                ON CONFLICT(match_id, market) DO UPDATE SET
                    prediction_id=excluded.prediction_id,
                    championship=excluded.championship,
                    home_team=excluded.home_team,
                    away_team=excluded.away_team,
                    predicted_pick=excluded.predicted_pick,
                    predicted_prob=excluded.predicted_prob,
                    confidence=excluded.confidence,
                    predicted_at_unix=excluded.predicted_at_unix,
                    kickoff_unix=excluded.kickoff_unix;
                """,
                (
                    pid,
                    mid,
                    champ,
                    str(home_team or ""),
                    str(away_team or ""),
                    mk,
                    pick,
                    float(prob),
                    float(conf),
                    float(predicted_at_unix),
                    float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None,
                ),
            )

    def _db_resolve_predictions_for_match(
        self,
        *,
        match_id: str,
        final_outcome: str,
        final_home_goals: int,
        final_away_goals: int,
        resolved_at_unix: float,
    ) -> int:
        if not self._db_enabled:
            return 0
        mid = str(match_id or "").strip()
        outc = str(final_outcome or "").strip()
        if not mid or not outc:
            return 0
        with sqlite3.connect(self._db_path, timeout=5) as con:
            cur = con.execute(
                """
                UPDATE predictions_history
                SET
                    final_outcome=?,
                    final_home_goals=?,
                    final_away_goals=?,
                    correct=CASE WHEN predicted_pick=? THEN 1 ELSE 0 END,
                    roi_simulated=CASE WHEN predicted_pick=? THEN 1.0 ELSE -1.0 END,
                    resolved_at_unix=?
                WHERE match_id=?
                  AND resolved_at_unix IS NULL;
                """,
                (
                    outc,
                    int(final_home_goals),
                    int(final_away_goals),
                    outc,
                    outc,
                    float(resolved_at_unix),
                    mid,
                ),
            )
        try:
            return int(cur.rowcount or 0)
        except Exception:
            return 0

    def _db_list_prediction_history(
        self,
        *,
        championship: str | None,
        resolved_only: bool,
        since_unix: float | None,
        limit: int,
    ) -> list[tuple]:
        if not self._db_enabled:
            return []
        lim = int(limit)
        if lim <= 0:
            lim = 100
        if lim > 5000:
            lim = 5000
        champ = str(championship or "").strip()
        resolved_clause = "AND resolved_at_unix IS NOT NULL" if bool(resolved_only) else ""
        since_clause = "AND predicted_at_unix >= ?" if isinstance(since_unix, (int, float)) and float(since_unix) > 0 else ""
        params: list[Any] = []
        q = f"""
            SELECT
                prediction_id,
                match_id,
                championship,
                home_team,
                away_team,
                market,
                predicted_pick,
                predicted_prob,
                confidence,
                predicted_at_unix,
                kickoff_unix,
                final_outcome,
                correct,
                roi_simulated,
                resolved_at_unix
            FROM predictions_history
            WHERE 1=1
        """
        if champ and champ != "all":
            q += " AND championship=?"
            params.append(champ)
        if resolved_clause:
            q += f" {resolved_clause}"
        if since_clause:
            q += f" {since_clause}"
            params.append(float(since_unix))  # type: ignore[arg-type]
        q += " ORDER BY COALESCE(resolved_at_unix, predicted_at_unix) DESC LIMIT ?;"
        params.append(int(lim))
        with sqlite3.connect(self._db_path, timeout=5) as con:
            rows = con.execute(q, tuple(params)).fetchall()
        return [r for r in rows if isinstance(r, tuple)]

    def _db_list_resolved_predictions_since(self, *, championship: str | None, since_unix: float) -> list[tuple]:
        if not self._db_enabled:
            return []
        champ = str(championship or "").strip()
        since0 = float(since_unix)
        params: list[Any] = [since0]
        q = """
            SELECT
                match_id,
                championship,
                predicted_pick,
                predicted_prob,
                confidence,
                final_outcome,
                correct,
                roi_simulated,
                resolved_at_unix
            FROM predictions_history
            WHERE resolved_at_unix IS NOT NULL
              AND resolved_at_unix >= ?
        """
        if champ and champ != "all":
            q += " AND championship=?"
            params.append(champ)
        q += " ORDER BY resolved_at_unix ASC;"
        with sqlite3.connect(self._db_path, timeout=5) as con:
            rows = con.execute(q, tuple(params)).fetchall()
        return [r for r in rows if isinstance(r, tuple)]

    def _db_insert_notification_if_new(self, *, notification_key: str, ntype: str, payload_json: str, now_unix: float) -> str | None:
        if not self._db_enabled:
            return None
        key = str(notification_key or "").strip()
        if not key:
            return None
        nid = str(uuid.uuid4())
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT OR IGNORE INTO notifications_outbox (
                    notification_id, notification_key, type, payload_json, created_at_unix, sent_email
                ) VALUES (?, ?, ?, ?, ?, 0);
                """,
                (nid, key, str(ntype), str(payload_json), float(now_unix)),
            )
            row = con.execute("SELECT notification_id FROM notifications_outbox WHERE notification_key=?;", (key,)).fetchone()
        if not isinstance(row, tuple) or not row:
            return None
        return str(row[0])

    def _db_mark_notification_email_sent(self, *, notification_id: str) -> None:
        if not self._db_enabled:
            return
        nid = str(notification_id or "").strip()
        if not nid:
            return
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute("UPDATE notifications_outbox SET sent_email=1 WHERE notification_id=?;", (nid,))

    def _db_list_notifications(self, *, limit: int) -> list[tuple[str, str, str, float, int]]:
        if not self._db_enabled:
            return []
        lim = int(limit)
        if lim <= 0:
            lim = 50
        if lim > 500:
            lim = 500
        with sqlite3.connect(self._db_path, timeout=5) as con:
            rows = con.execute(
                """
                SELECT notification_id, type, payload_json, created_at_unix, sent_email
                FROM notifications_outbox
                ORDER BY created_at_unix DESC
                LIMIT ?;
                """,
                (int(lim),),
            ).fetchall()
        out: list[tuple[str, str, str, float, int]] = []
        for r in rows:
            if not isinstance(r, tuple) or len(r) < 5:
                continue
            try:
                out.append((str(r[0]), str(r[1]), str(r[2]), float(r[3]), int(r[4] or 0)))
            except Exception:
                continue
        return out

    def _db_get_notification_preferences(self, *, user_id: str) -> dict[str, Any] | None:
        if not self._db_enabled:
            return None
        uid = str(user_id or "").strip() or "default"
        with sqlite3.connect(self._db_path, timeout=5) as con:
            row = con.execute(
                """
                SELECT enabled, channels_json, quiet_hours_json, max_per_day, min_interval_minutes, updated_at_unix
                FROM notification_preferences
                WHERE user_id=?;
                """,
                (uid,),
            ).fetchone()
        if not isinstance(row, tuple) or len(row) < 6:
            return None
        enabled, channels_json, quiet_hours_json, max_per_day, min_interval_minutes, updated_at_unix = row
        try:
            channels = json.loads(channels_json) if isinstance(channels_json, str) else []
        except Exception:
            channels = []
        try:
            quiet_hours = json.loads(quiet_hours_json) if isinstance(quiet_hours_json, str) else [22, 8]
        except Exception:
            quiet_hours = [22, 8]
        return {
            "user_id": uid,
            "enabled": bool(int(enabled or 0)),
            "channels": channels if isinstance(channels, list) else [],
            "quiet_hours": quiet_hours if isinstance(quiet_hours, list) else [22, 8],
            "max_per_day": int(max_per_day or 0),
            "min_interval_minutes": int(min_interval_minutes or 0),
            "updated_at_unix": float(updated_at_unix or 0.0),
        }

    def _db_upsert_notification_preferences(
        self,
        *,
        user_id: str,
        enabled: bool,
        channels_json: str,
        quiet_hours_json: str,
        max_per_day: int,
        min_interval_minutes: int,
        updated_at_unix: float,
    ) -> None:
        if not self._db_enabled:
            return
        uid = str(user_id or "").strip() or "default"
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT INTO notification_preferences (
                    user_id, enabled, channels_json, quiet_hours_json, max_per_day, min_interval_minutes, updated_at_unix
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    channels_json=excluded.channels_json,
                    quiet_hours_json=excluded.quiet_hours_json,
                    max_per_day=excluded.max_per_day,
                    min_interval_minutes=excluded.min_interval_minutes,
                    updated_at_unix=excluded.updated_at_unix;
                """,
                (
                    uid,
                    1 if bool(enabled) else 0,
                    str(channels_json),
                    str(quiet_hours_json),
                    int(max_per_day),
                    int(min_interval_minutes),
                    float(updated_at_unix),
                ),
            )

    def _db_get_tenant_config(self, *, tenant_id: str) -> dict[str, Any] | None:
        if not self._db_enabled:
            return None
        tid = str(tenant_id or "").strip() or "default"
        with sqlite3.connect(self._db_path, timeout=5) as con:
            row = con.execute(
                """
                SELECT config_json, updated_at_unix
                FROM tenant_config
                WHERE tenant_id=?;
                """,
                (tid,),
            ).fetchone()
        if not isinstance(row, tuple) or len(row) < 2:
            return None
        config_json, updated_at_unix = row
        try:
            cfg = json.loads(config_json) if isinstance(config_json, str) else {}
        except Exception:
            cfg = {}
        return {
            "tenant_id": tid,
            "config": cfg if isinstance(cfg, dict) else {},
            "updated_at_unix": float(updated_at_unix or 0.0),
        }

    def _db_upsert_tenant_config(self, *, tenant_id: str, config_json: str, updated_at_unix: float) -> None:
        if not self._db_enabled:
            return
        tid = str(tenant_id or "").strip() or "default"
        with sqlite3.connect(self._db_path, timeout=5) as con:
            con.execute(
                """
                INSERT INTO tenant_config (tenant_id, config_json, updated_at_unix)
                VALUES (?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    config_json=excluded.config_json,
                    updated_at_unix=excluded.updated_at_unix;
                """,
                (tid, str(config_json), float(updated_at_unix)),
            )

    def _db_list_notification_preferences(self) -> list[dict[str, Any]]:
        if not self._db_enabled:
            return []
        with sqlite3.connect(self._db_path, timeout=5) as con:
            rows = con.execute(
                """
                SELECT user_id, enabled, channels_json, quiet_hours_json, max_per_day, min_interval_minutes, updated_at_unix
                FROM notification_preferences;
                """
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, tuple) or len(row) < 7:
                continue
            user_id, enabled, channels_json, quiet_hours_json, max_per_day, min_interval_minutes, updated_at_unix = row
            try:
                channels = json.loads(channels_json) if isinstance(channels_json, str) else []
            except Exception:
                channels = []
            try:
                quiet_hours = json.loads(quiet_hours_json) if isinstance(quiet_hours_json, str) else [22, 8]
            except Exception:
                quiet_hours = [22, 8]
            out.append(
                {
                    "user_id": str(user_id or "default"),
                    "enabled": bool(int(enabled or 0)),
                    "channels": channels if isinstance(channels, list) else [],
                    "quiet_hours": quiet_hours if isinstance(quiet_hours, list) else [22, 8],
                    "max_per_day": int(max_per_day or 0),
                    "min_interval_minutes": int(min_interval_minutes or 0),
                    "updated_at_unix": float(updated_at_unix or 0.0),
                }
            )
        return out

    def _db_log_delivery_if_new(self, *, user_id: str, channel: str, notification_key: str, ntype: str, now_unix: float) -> bool:
        if not self._db_enabled:
            return False
        uid = str(user_id or "").strip() or "default"
        ch = str(channel or "").strip().lower()
        key = str(notification_key or "").strip()
        if not ch or not key:
            return False
        day_utc = time.strftime("%Y-%m-%d", time.gmtime(float(now_unix)))
        with sqlite3.connect(self._db_path, timeout=5) as con:
            existed = con.execute(
                """
                SELECT 1
                FROM notifications_delivery_log
                WHERE user_id=? AND channel=? AND notification_key=?;
                """,
                (uid, ch, key),
            ).fetchone()
            if isinstance(existed, tuple) and existed:
                return False
            con.execute(
                """
                INSERT OR IGNORE INTO notifications_delivery_log (
                    user_id, channel, notification_key, type, sent_at_unix, day_utc
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (uid, ch, key, str(ntype), float(now_unix), str(day_utc)),
            )
        return True

    def _db_get_delivery_stats(self, *, user_id: str, channel: str, now_unix: float) -> tuple[int, float]:
        if not self._db_enabled:
            return (0, 0.0)
        uid = str(user_id or "").strip() or "default"
        ch = str(channel or "").strip().lower()
        day_utc = time.strftime("%Y-%m-%d", time.gmtime(float(now_unix)))
        with sqlite3.connect(self._db_path, timeout=5) as con:
            row = con.execute(
                """
                SELECT COUNT(*)
                FROM notifications_delivery_log
                WHERE user_id=? AND channel=? AND day_utc=?;
                """,
                (uid, ch, str(day_utc)),
            ).fetchone()
            row2 = con.execute(
                """
                SELECT sent_at_unix
                FROM notifications_delivery_log
                WHERE user_id=? AND channel=?
                ORDER BY sent_at_unix DESC
                LIMIT 1;
                """,
                (uid, ch),
            ).fetchone()
        cnt = int(row[0] or 0) if isinstance(row, tuple) and row else 0
        last = float(row2[0] or 0.0) if isinstance(row2, tuple) and row2 else 0.0
        return (cnt, last)

    def _db_select_finished_rows(self, championship: str, since_unix: float) -> list[tuple[str, str]]:
        if not self._db_enabled:
            return []
        champ = str(championship or "").strip()
        with sqlite3.connect(self._db_path, timeout=5) as con:
            if champ and champ != "all":
                rows = con.execute(
                    """
                    SELECT probabilities_json, meta_json
                    FROM matches
                    WHERE status='FINISHED'
                      AND championship=?
                      AND kickoff_unix IS NOT NULL
                      AND kickoff_unix >= ?
                      AND final_home_goals IS NOT NULL
                      AND final_away_goals IS NOT NULL
                    ORDER BY kickoff_unix DESC
                    LIMIT 800;
                    """,
                    (champ, float(since_unix)),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT probabilities_json, meta_json
                    FROM matches
                    WHERE status='FINISHED'
                      AND kickoff_unix IS NOT NULL
                      AND kickoff_unix >= ?
                      AND final_home_goals IS NOT NULL
                      AND final_away_goals IS NOT NULL
                    ORDER BY kickoff_unix DESC
                    LIMIT 1200;
                    """,
                    (float(since_unix),),
                ).fetchall()
        return [(str(r[0]), str(r[1])) for r in rows if isinstance(r, tuple) and len(r) >= 2]

    async def upsert_match(self, match: LiveMatchState) -> None:
        row: dict[str, Any] | None = None
        resolved: tuple[str, int, int] | None = None
        async with self._lock:
            self.matches[match.match_id] = match
            fs = self._extract_final_score(match)
            if match.status == "FINISHED" and fs is not None:
                self._calibration_dirty = True
                resolved = (self._outcome_from_score(fs[0], fs[1]), int(fs[0]), int(fs[1]))
            row = {
                "match_id": match.match_id,
                "championship": match.championship,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "status": match.status,
                "matchday": match.matchday,
                "kickoff_unix": match.kickoff_unix,
                "next_update_unix": match.next_update_unix,
                "updated_at_unix": match.updated_at_unix,
                "probabilities_json": json.dumps(match.probabilities or {}, ensure_ascii=False, separators=(",", ":")),
                "meta_json": json.dumps(match.meta or {}, ensure_ascii=False, separators=(",", ":")),
                "final_home_goals": fs[0] if fs is not None else None,
                "final_away_goals": fs[1] if fs is not None else None,
            }
        if row is not None and self._db_enabled:
            await asyncio.to_thread(self._db_upsert_match, row)
            if resolved is not None:
                await asyncio.to_thread(
                    self._db_resolve_predictions_for_match,
                    match_id=str(match.match_id),
                    final_outcome=str(resolved[0]),
                    final_home_goals=int(resolved[1]),
                    final_away_goals=int(resolved[2]),
                    resolved_at_unix=float(time.time()),
                )

    async def get_match(self, match_id: str) -> LiveMatchState | None:
        async with self._lock:
            return self.matches.get(match_id)

    async def list_matches(self) -> list[LiveMatchState]:
        async with self._lock:
            return list(self.matches.values())

    async def clear_all(self) -> None:
        async with self._lock:
            self.matches = {}
            self._calibration_cache = {}
            self._calibration_dirty = True
        if self._db_enabled:
            await asyncio.to_thread(self._db_clear_all)

    async def get_cache_json(self, cache_key: str) -> Any | None:
        if not self._db_enabled:
            return None
        raw = await asyncio.to_thread(self._db_get_cache, cache_key, float(time.time()))
        if not isinstance(raw, str) or not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def set_cache_json(self, cache_key: str, payload: Any, ttl_seconds: float) -> None:
        if not self._db_enabled:
            return
        try:
            ttl = float(ttl_seconds)
        except Exception:
            return
        if ttl <= 0:
            return
        try:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return
        await asyncio.to_thread(self._db_set_cache, cache_key, raw, float(time.time()), ttl)

    async def upsert_odds(self, *, match_id: str, market: str, odds: float, source: str | None = None) -> None:
        if not self._db_enabled:
            return
        await asyncio.to_thread(
            self._db_upsert_odds,
            match_id=str(match_id),
            market=str(market),
            odds=float(odds),
            source=str(source) if source is not None else None,
            now_unix=float(time.time()),
        )

    async def list_odds(self, *, limit: int = 200) -> list[dict[str, Any]]:
        if not self._db_enabled:
            return []
        rows = await asyncio.to_thread(self._db_list_odds, limit=int(limit))
        out: list[dict[str, Any]] = []
        for match_id, market, odds, source, updated_at_unix in rows:
            out.append(
                {
                    "match_id": str(match_id),
                    "market": str(market),
                    "odds": float(odds),
                    "source": str(source) if source is not None else None,
                    "updated_at_unix": float(updated_at_unix),
                }
            )
        return out

    async def upsert_prediction_history(
        self,
        *,
        match_id: str,
        championship: str,
        home_team: str,
        away_team: str,
        market: str,
        predicted_pick: str,
        predicted_prob: float,
        confidence: float,
        kickoff_unix: float | None,
    ) -> None:
        if not self._db_enabled:
            return
        mid = str(match_id or "").strip()
        mk = str(market or "").strip().upper()
        if not mid or not mk:
            return
        pid = f"{mid}:{mk}"
        await asyncio.to_thread(
            self._db_upsert_prediction_history,
            prediction_id=str(pid),
            match_id=str(mid),
            championship=str(championship),
            home_team=str(home_team),
            away_team=str(away_team),
            market=str(mk),
            predicted_pick=str(predicted_pick),
            predicted_prob=float(predicted_prob),
            confidence=float(confidence),
            predicted_at_unix=float(time.time()),
            kickoff_unix=float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None,
        )

    async def list_prediction_history(
        self,
        *,
        championship: str | None = None,
        resolved_only: bool = True,
        since_unix: float | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        if not self._db_enabled:
            return []
        rows = await asyncio.to_thread(
            self._db_list_prediction_history,
            championship=str(championship) if championship is not None else None,
            resolved_only=bool(resolved_only),
            since_unix=float(since_unix) if isinstance(since_unix, (int, float)) else None,
            limit=int(limit),
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, tuple) or len(r) < 15:
                continue
            (
                prediction_id,
                match_id,
                champ,
                home_team,
                away_team,
                market,
                predicted_pick,
                predicted_prob,
                confidence,
                predicted_at_unix,
                kickoff_unix,
                final_outcome,
                correct,
                roi_simulated,
                resolved_at_unix,
            ) = r[:15]
            out.append(
                {
                    "prediction_id": str(prediction_id),
                    "match_id": str(match_id),
                    "championship": str(champ),
                    "home_team": str(home_team),
                    "away_team": str(away_team),
                    "market": str(market),
                    "predicted_pick": str(predicted_pick),
                    "predicted_prob": float(predicted_prob or 0.0),
                    "confidence": float(confidence or 0.0),
                    "predicted_at_unix": float(predicted_at_unix or 0.0),
                    "kickoff_unix": float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None,
                    "final_outcome": str(final_outcome) if final_outcome is not None else None,
                    "correct": bool(int(correct or 0)) if correct is not None else None,
                    "roi_simulated": float(roi_simulated) if isinstance(roi_simulated, (int, float)) else None,
                    "resolved_at_unix": float(resolved_at_unix) if isinstance(resolved_at_unix, (int, float)) else None,
                }
            )
        return out

    async def list_resolved_predictions_since(
        self,
        *,
        championship: str | None,
        since_unix: float,
    ) -> list[dict[str, Any]]:
        if not self._db_enabled:
            return []
        rows = await asyncio.to_thread(
            self._db_list_resolved_predictions_since,
            championship=str(championship) if championship is not None else None,
            since_unix=float(since_unix),
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, tuple) or len(r) < 9:
                continue
            match_id, champ, predicted_pick, predicted_prob, confidence, final_outcome, correct, roi_simulated, resolved_at_unix = r[:9]
            out.append(
                {
                    "match_id": str(match_id),
                    "championship": str(champ),
                    "predicted_pick": str(predicted_pick),
                    "predicted_prob": float(predicted_prob or 0.0),
                    "confidence": float(confidence or 0.0),
                    "final_outcome": str(final_outcome),
                    "correct": bool(int(correct or 0)),
                    "roi_simulated": float(roi_simulated or 0.0),
                    "resolved_at_unix": float(resolved_at_unix or 0.0),
                }
            )
        return out

    async def insert_notification_if_new(self, *, notification_key: str, ntype: str, payload: dict[str, Any]) -> str | None:
        if not self._db_enabled:
            return None
        try:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            raw = "{}"
        return await asyncio.to_thread(
            self._db_insert_notification_if_new,
            notification_key=str(notification_key),
            ntype=str(ntype),
            payload_json=str(raw),
            now_unix=float(time.time()),
        )

    async def mark_notification_email_sent(self, *, notification_id: str) -> None:
        if not self._db_enabled:
            return
        await asyncio.to_thread(self._db_mark_notification_email_sent, notification_id=str(notification_id))

    async def list_notifications(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._db_enabled:
            return []
        rows = await asyncio.to_thread(self._db_list_notifications, limit=int(limit))
        out: list[dict[str, Any]] = []
        for notification_id, ntype, payload_json, created_at_unix, sent_email in rows:
            try:
                payload = json.loads(payload_json) if isinstance(payload_json, str) else {}
            except Exception:
                payload = {}
            out.append(
                {
                    "notification_id": str(notification_id),
                    "type": str(ntype),
                    "created_at_unix": float(created_at_unix),
                    "sent_email": bool(int(sent_email or 0)),
                    "payload": payload if isinstance(payload, dict) else {},
                }
            )
        return out

    async def get_notification_preferences(self, *, user_id: str = "default") -> dict[str, Any]:
        if not self._db_enabled:
            return {
                "user_id": str(user_id or "default"),
                "enabled": False,
                "channels": ["push"],
                "quiet_hours": [22, 8],
                "max_per_day": 5,
                "min_interval_minutes": 30,
                "updated_at_unix": 0.0,
            }
        row = await asyncio.to_thread(self._db_get_notification_preferences, user_id=str(user_id or "default"))
        if isinstance(row, dict) and row:
            return row
        return {
            "user_id": str(user_id or "default"),
            "enabled": False,
            "channels": ["push"],
            "quiet_hours": [22, 8],
            "max_per_day": 5,
            "min_interval_minutes": 30,
            "updated_at_unix": 0.0,
        }

    async def upsert_notification_preferences(
        self,
        *,
        user_id: str = "default",
        enabled: bool,
        channels: list[str],
        quiet_hours: list[int],
        max_per_day: int,
        min_interval_minutes: int,
    ) -> dict[str, Any]:
        if not self._db_enabled:
            return await self.get_notification_preferences(user_id=str(user_id or "default"))
        uid = str(user_id or "default")
        ch = [str(x).strip().lower() for x in (channels or []) if str(x).strip()]
        qh = [int(x) for x in (quiet_hours or []) if isinstance(x, int)]
        if len(qh) != 2:
            qh = [22, 8]
        mpd = int(max_per_day)
        if mpd <= 0:
            mpd = 5
        if mpd > 50:
            mpd = 50
        mim = int(min_interval_minutes)
        if mim < 0:
            mim = 0
        if mim > 24 * 60:
            mim = 24 * 60
        now_unix = float(time.time())
        await asyncio.to_thread(
            self._db_upsert_notification_preferences,
            user_id=uid,
            enabled=bool(enabled),
            channels_json=json.dumps(ch, ensure_ascii=False, separators=(",", ":")),
            quiet_hours_json=json.dumps(qh, ensure_ascii=False, separators=(",", ":")),
            max_per_day=int(mpd),
            min_interval_minutes=int(mim),
            updated_at_unix=float(now_unix),
        )
        return await self.get_notification_preferences(user_id=uid)

    async def list_notification_preferences(self) -> list[dict[str, Any]]:
        if not self._db_enabled:
            return []
        rows = await asyncio.to_thread(self._db_list_notification_preferences)
        return rows if isinstance(rows, list) else []

    async def get_tenant_config(self, *, tenant_id: str = "default") -> dict[str, Any]:
        tid = str(tenant_id or "").strip() or "default"
        if not self._db_enabled:
            return {"tenant_id": tid, "config": {}, "updated_at_unix": 0.0}
        row = await asyncio.to_thread(self._db_get_tenant_config, tenant_id=tid)
        if isinstance(row, dict) and row:
            return row
        return {"tenant_id": tid, "config": {}, "updated_at_unix": 0.0}

    async def upsert_tenant_config(self, *, tenant_id: str = "default", config: dict[str, Any]) -> dict[str, Any]:
        tid = str(tenant_id or "").strip() or "default"
        if not self._db_enabled:
            return {"tenant_id": tid, "config": config if isinstance(config, dict) else {}, "updated_at_unix": 0.0}
        cfg = config if isinstance(config, dict) else {}
        try:
            raw = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            raw = "{}"
        now_unix = float(time.time())
        await asyncio.to_thread(self._db_upsert_tenant_config, tenant_id=tid, config_json=str(raw), updated_at_unix=float(now_unix))
        return await self.get_tenant_config(tenant_id=tid)

    async def log_delivery_if_new(self, *, user_id: str, channel: str, notification_key: str, ntype: str) -> bool:
        if not self._db_enabled:
            return False
        return await asyncio.to_thread(
            self._db_log_delivery_if_new,
            user_id=str(user_id or "default"),
            channel=str(channel or ""),
            notification_key=str(notification_key or ""),
            ntype=str(ntype or ""),
            now_unix=float(time.time()),
        )

    async def get_delivery_stats(self, *, user_id: str, channel: str) -> tuple[int, float]:
        if not self._db_enabled:
            return (0, 0.0)
        return await asyncio.to_thread(
            self._db_get_delivery_stats,
            user_id=str(user_id or "default"),
            channel=str(channel or ""),
            now_unix=float(time.time()),
        )

    async def get_calibration_alpha(self, championship: str) -> float:
        champ = str(championship or "").strip() or "all"
        now = time.time()
        cached = self._calibration_cache.get(champ)
        if cached is not None and (now - float(cached[1])) < 600.0 and not self._calibration_dirty:
            return float(cached[0])

        lookback_days = int(getattr(settings, "calibration_lookback_days", 365) or 365)
        lookback_days = max(30, min(3 * 365, lookback_days))
        since_unix = now - float(lookback_days) * 86400.0

        rows = await asyncio.to_thread(self._db_select_finished_rows, champ, float(since_unix))
        pairs: list[tuple[dict[str, float], str]] = []
        for probs_json, meta_json in rows:
            try:
                probs0 = json.loads(probs_json) if isinstance(probs_json, str) else {}
            except Exception:
                probs0 = {}
            if not isinstance(probs0, dict):
                continue
            try:
                meta0 = json.loads(meta_json) if isinstance(meta_json, str) else {}
            except Exception:
                meta0 = {}
            ctx = meta0.get("context") if isinstance(meta0, dict) else None
            if not isinstance(ctx, dict):
                continue
            fs = ctx.get("final_score")
            if not isinstance(fs, dict):
                continue
            hg = fs.get("home")
            ag = fs.get("away")
            if not isinstance(hg, int) or not isinstance(ag, int):
                continue
            if hg > ag:
                outcome = "home_win"
            elif hg == ag:
                outcome = "draw"
            else:
                outcome = "away_win"

            p1 = float(probs0.get("home_win", 0.0) or 0.0)
            px = float(probs0.get("draw", 0.0) or 0.0)
            p2 = float(probs0.get("away_win", 0.0) or 0.0)
            s = max(p1, 0.0) + max(px, 0.0) + max(p2, 0.0)
            if s <= 0:
                probs = {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
            else:
                probs = {"home_win": max(p1, 0.0) / s, "draw": max(px, 0.0) / s, "away_win": max(p2, 0.0) / s}
            pairs.append((probs, outcome))

        if len(pairs) < 30:
            alpha = 0.0
            self._calibration_cache[champ] = (float(alpha), now)
            self._calibration_dirty = False
            return float(alpha)

        def brier(alpha0: float) -> float:
            s0 = 0.0
            for probs, outcome in pairs:
                p1 = (1.0 - alpha0) * float(probs["home_win"]) + alpha0 / 3.0
                px = (1.0 - alpha0) * float(probs["draw"]) + alpha0 / 3.0
                p2 = (1.0 - alpha0) * float(probs["away_win"]) + alpha0 / 3.0
                if outcome == "home_win":
                    o1, ox, o2 = 1.0, 0.0, 0.0
                elif outcome == "draw":
                    o1, ox, o2 = 0.0, 1.0, 0.0
                else:
                    o1, ox, o2 = 0.0, 0.0, 1.0
                s0 += ((p1 - o1) ** 2 + (px - ox) ** 2 + (p2 - o2) ** 2) / 3.0
            return s0 / float(len(pairs))

        best_a = 0.0
        best_loss = brier(0.0)
        for i in range(1, 31):
            a0 = i / 100.0
            loss = brier(a0)
            if loss < best_loss:
                best_loss = loss
                best_a = a0

        self._calibration_cache[champ] = (float(best_a), now)
        self._calibration_dirty = False
        return float(best_a)
