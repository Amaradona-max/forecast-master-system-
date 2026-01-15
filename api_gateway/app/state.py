from __future__ import annotations

import asyncio
import json
import sqlite3
import time
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
        async with self._lock:
            self.matches[match.match_id] = match
            fs = self._extract_final_score(match)
            if match.status == "FINISHED" and fs is not None:
                self._calibration_dirty = True
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
