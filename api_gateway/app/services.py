from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from ml_engine.ensemble_predictor.service import EnsemblePredictorService
from ml_engine.cache.cache_keys import build_cache_key, stable_json_hash
from ml_engine.cache.sqlite_cache import SqliteCache
from ml_engine.features.schema import FEATURE_VERSION
from ml_engine.resilience.degradation import build_degradation
from ml_engine.resilience.timeouts import time_left_ms
from ml_engine.config import artifact_dir, cache_db_path
from api_gateway.app.chaos_index import compute_chaos
from api_gateway.app.calibration_temperature import apply_temperature
from api_gateway.app.decision_gate import adjust_thresholds_for_chaos, evaluate_decision, load_tuned_thresholds, select_thresholds
from api_gateway.app.settings import settings
from api_gateway.app.team_name_resolver import TeamNameResolver
from api_gateway.app.team_name_resolver import canonicalize


@dataclass(frozen=True)
class PredictionResult:
    probabilities: dict[str, float]
    explain: dict[str, Any]
    confidence: float | None = None
    ranges: dict[str, Any] | None = None


class PredictionService:
    def __init__(self) -> None:
        self._ensemble = EnsemblePredictorService()
        self._team_resolver = TeamNameResolver(
            aliases_path=str(getattr(settings, "team_aliases_path", "data/team_aliases.json")),
            enable_fuzzy=bool(getattr(settings, "team_aliases_enable_fuzzy", True)),
            fuzzy_cutoff=float(getattr(settings, "team_aliases_fuzzy_cutoff", 0.86)),
        )
        self._decision_gate_tuned_cache: dict[str, Any] | None = None
        self._decision_gate_tuned_mtime_ns: int | None = None
        self._team_dynamics_cache: dict[str, Any] | None = None
        self._team_dynamics_mtime_ns: int | None = None
        self._temperature_cache: dict[str, Any] | None = None
        self._temperature_mtime_ns: int | None = None
        self._drift_cache: dict[str, Any] | None = None
        self._drift_mtime_ns: int | None = None

    def _calibrate_probs(self, probs: dict[str, float], alpha: float) -> dict[str, float]:
        try:
            a = float(alpha)
        except Exception:
            a = 0.0
        if a <= 0.0:
            return probs
        if a > 0.35:
            a = 0.35
        p1 = float(probs.get("home_win", 0.0) or 0.0)
        px = float(probs.get("draw", 0.0) or 0.0)
        p2 = float(probs.get("away_win", 0.0) or 0.0)
        s = max(p1, 0.0) + max(px, 0.0) + max(p2, 0.0)
        if s <= 0:
            p1, px, p2 = 1 / 3, 1 / 3, 1 / 3
        else:
            p1, px, p2 = max(p1, 0.0) / s, max(px, 0.0) / s, max(p2, 0.0) / s
        p1 = (1.0 - a) * p1 + a / 3.0
        px = (1.0 - a) * px + a / 3.0
        p2 = (1.0 - a) * p2 + a / 3.0
        s2 = p1 + px + p2
        if s2 <= 0:
            return {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
        return {"home_win": p1 / s2, "draw": px / s2, "away_win": p2 / s2}

    def _artifact_version(self, path: Path) -> str:
        try:
            st = path.stat()
        except Exception:
            return "missing"
        return str(int(st.st_mtime_ns))

    def _load_team_form(self) -> dict[str, Any] | None:
        try:
            p = Path(str(getattr(settings, "form_path", "data/team_form.json")))
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_team_dynamics(self) -> dict[str, Any] | None:
        try:
            p = Path(str(getattr(settings, "team_dynamics_path", "data/team_dynamics.json")))
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_json_cached(self, path: str, cache_attr: str, mtime_attr: str) -> dict[str, Any] | None:
        p = Path(str(path))
        if not p.exists():
            setattr(self, cache_attr, None)
            setattr(self, mtime_attr, None)
            return None
        mt = p.stat().st_mtime_ns
        prev = getattr(self, mtime_attr, None)
        if prev == mt and getattr(self, cache_attr, None) is not None:
            return getattr(self, cache_attr)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                setattr(self, cache_attr, data)
                setattr(self, mtime_attr, mt)
                return data
        except Exception:
            pass
        setattr(self, cache_attr, None)
        setattr(self, mtime_attr, mt)
        return None

    def _apply_kickoff_context(self, *, kickoff_unix: float | None, ctx: dict[str, Any]) -> None:
        if not isinstance(kickoff_unix, (int, float)):
            return
        try:
            dt = datetime.fromtimestamp(float(kickoff_unix), tz=timezone.utc)
        except Exception:
            return
        if not isinstance(ctx.get("month"), (int, float)):
            ctx["month"] = float(dt.month)
        if not isinstance(ctx.get("weekday"), (int, float)):
            ctx["weekday"] = float(dt.weekday())
        if not isinstance(ctx.get("season_year"), (int, float)):
            season_year = dt.year if dt.month >= 7 else dt.year - 1
            ctx["season_year"] = float(season_year)

    def _lookup_team_dynamics_row(self, *, champ_block: dict[str, Any], team: str) -> dict[str, Any] | None:
        teams = champ_block.get("teams")
        if not isinstance(teams, dict):
            return None
        row = teams.get(team)
        if isinstance(row, dict):
            return row
        can_map: dict[str, str] = {}
        for k in teams.keys():
            if not isinstance(k, str):
                continue
            ck = canonicalize(k)
            if ck and ck not in can_map:
                can_map[ck] = k
        can = canonicalize(str(team))
        if can:
            mapped = can_map.get(can)
            if isinstance(mapped, str):
                row2 = teams.get(mapped)
                if isinstance(row2, dict):
                    return row2
            if bool(getattr(settings, "team_aliases_enable_fuzzy", True)) and can_map:
                cutoff = float(getattr(settings, "team_aliases_fuzzy_cutoff", 0.86) or 0.86)
                best = get_close_matches(can, list(can_map.keys()), n=1, cutoff=cutoff)
                if best:
                    mapped2 = can_map.get(best[0])
                    if isinstance(mapped2, str):
                        row3 = teams.get(mapped2)
                        if isinstance(row3, dict):
                            return row3
        return None

    def _last_before(self, kickoffs: list[float], *, kickoff_unix: float) -> float | None:
        prev = [k for k in kickoffs if float(k) < float(kickoff_unix)]
        if not prev:
            return None
        return float(max(prev))

    def _apply_rest_days(
        self,
        *,
        championship: str,
        home_team: str,
        away_team: str,
        kickoff_unix: float | None,
        ctx: dict[str, Any],
    ) -> None:
        if not isinstance(kickoff_unix, (int, float)):
            return
        data = self._load_team_dynamics()
        if not isinstance(data, dict):
            return
        champs = data.get("championships")
        if not isinstance(champs, dict):
            return
        champ_block = champs.get(str(championship))
        if not isinstance(champ_block, dict):
            return

        def _rest_for(team: str) -> float | None:
            row = self._lookup_team_dynamics_row(champ_block=champ_block, team=str(team))
            if not isinstance(row, dict):
                return None
            ks = row.get("recent_kickoffs")
            if not isinstance(ks, list):
                return None
            kickoffs = [float(x) for x in ks if isinstance(x, (int, float))]
            if not kickoffs:
                return None
            last = self._last_before(kickoffs, kickoff_unix=float(kickoff_unix))
            if last is None:
                return None
            rest = (float(kickoff_unix) - float(last)) / 86400.0
            if rest < 0:
                return None
            return float(rest)

        def _set_if_missing(key: str, value: float | None) -> None:
            if isinstance(ctx.get(key), (int, float)):
                return
            if value is None:
                return
            ctx[key] = float(value)

        h_rest = _rest_for(str(home_team))
        a_rest = _rest_for(str(away_team))
        _set_if_missing("home_days_rest", h_rest)
        _set_if_missing("away_days_rest", a_rest)
        if not isinstance(ctx.get("rest_diff"), (int, float)):
            if isinstance(ctx.get("home_days_rest"), (int, float)) and isinstance(ctx.get("away_days_rest"), (int, float)):
                ctx["rest_diff"] = float(ctx["home_days_rest"]) - float(ctx["away_days_rest"])

    def _apply_rest_from_team_dynamics(
        self,
        *,
        championship: str,
        home_team: str,
        away_team: str,
        kickoff_unix: float | None,
        ctx: dict,
    ) -> None:
        if not isinstance(kickoff_unix, (int, float)):
            return

        # se già presenti (dal client o da altro), non sovrascriviamo
        if any(k in ctx for k in ("home_days_rest", "away_days_rest", "rest_diff")):
            return

        data = self._load_team_dynamics()
        if not isinstance(data, dict):
            return
        champs = data.get("championships")
        if not isinstance(champs, dict):
            return
        champ_row = champs.get(str(championship))
        if not isinstance(champ_row, dict):
            return
        teams = champ_row.get("teams")
        if not isinstance(teams, dict):
            return

        # mappa canonical->nome originale come fai nel form
        can_map: dict[str, str] = {}
        for k in teams.keys():
            if isinstance(k, str):
                ck = canonicalize(k)
                if ck and ck not in can_map:
                    can_map[ck] = k

        def _lookup_recent_kickoffs(team_name: str) -> list[float] | None:
            row = teams.get(str(team_name))
            if isinstance(row, dict) and isinstance(row.get("recent_kickoffs"), list):
                return [float(x) for x in row["recent_kickoffs"] if isinstance(x, (int, float))]

            can = canonicalize(str(team_name))
            mapped = can_map.get(can) if can else None
            if isinstance(mapped, str):
                row2 = teams.get(mapped)
                if isinstance(row2, dict) and isinstance(row2.get("recent_kickoffs"), list):
                    return [float(x) for x in row2["recent_kickoffs"] if isinstance(x, (int, float))]

            return None

        def _rest_days(recent: list[float] | None) -> float | None:
            if not recent:
                return None
            # troviamo l'ultimo kickoff prima di quello corrente
            prev = None
            for ts in sorted(recent, reverse=True):
                if ts < float(kickoff_unix) - 60:  # buffer 1 min
                    prev = ts
                    break
            if prev is None:
                return None
            days = (float(kickoff_unix) - float(prev)) / 86400.0
            if days < 0:
                return None
            return float(days)

        rh = _rest_days(_lookup_recent_kickoffs(home_team))
        ra = _rest_days(_lookup_recent_kickoffs(away_team))

        if isinstance(rh, (int, float)):
            ctx.setdefault("home_days_rest", float(rh))
        if isinstance(ra, (int, float)):
            ctx.setdefault("away_days_rest", float(ra))
        if isinstance(rh, (int, float)) and isinstance(ra, (int, float)):
            ctx.setdefault("rest_diff", float(rh - ra))

    def _season_year_from_kickoff(self, kickoff_unix: float) -> int:
        dt = datetime.fromtimestamp(float(kickoff_unix), tz=timezone.utc)
        # stagioni calcio: tipicamente da luglio/agosto
        return int(dt.year if dt.month >= 7 else dt.year - 1)

    def _apply_time_context(self, ctx: dict, kickoff_unix: float | None) -> None:
        if not isinstance(kickoff_unix, (int, float)):
            return
        dt = datetime.fromtimestamp(float(kickoff_unix), tz=timezone.utc)

        # setdefault: se il client li manda, non li tocchiamo
        ctx.setdefault("month", float(dt.month))
        ctx.setdefault("weekday", float(dt.weekday()))
        ctx.setdefault("season_year", float(self._season_year_from_kickoff(float(kickoff_unix))))

    def _apply_form_context(self, *, championship: str, home_team: str, away_team: str, ctx: dict[str, Any]) -> None:
        keys = ["home_pts_last5", "away_pts_last5", "home_gf_last5", "home_ga_last5", "away_gf_last5", "away_ga_last5"]
        if any(k in ctx and isinstance(ctx.get(k), (int, float)) for k in keys):
            return
        data = self._load_team_form()
        if not isinstance(data, dict):
            return
        champs = data.get("championships")
        if not isinstance(champs, dict):
            return
        champ_row = champs.get(str(championship))
        if not isinstance(champ_row, dict):
            return
        teams = champ_row.get("teams")
        if not isinstance(teams, dict):
            return

        can_map: dict[str, str] = {}
        for k in teams.keys():
            if not isinstance(k, str):
                continue
            ck = canonicalize(k)
            if ck and ck not in can_map:
                can_map[ck] = k

        def _lookup(team_name: str) -> dict[str, Any] | None:
            row = teams.get(str(team_name))
            if isinstance(row, dict):
                return row
            can = canonicalize(str(team_name))
            if not can:
                return None
            mapped = can_map.get(can)
            if isinstance(mapped, str):
                row2 = teams.get(mapped)
                if isinstance(row2, dict):
                    return row2
            if bool(getattr(settings, "team_aliases_enable_fuzzy", True)) and can_map:
                cutoff = float(getattr(settings, "team_aliases_fuzzy_cutoff", 0.86) or 0.86)
                best = get_close_matches(can, list(can_map.keys()), n=1, cutoff=cutoff)
                if best:
                    mapped2 = can_map.get(best[0])
                    if isinstance(mapped2, str):
                        row3 = teams.get(mapped2)
                        if isinstance(row3, dict):
                            return row3
            return None

        hr = _lookup(str(home_team))
        ar = _lookup(str(away_team))
        if isinstance(hr, dict):
            ctx.setdefault("home_pts_last5", hr.get("pts_last5"))
            ctx.setdefault("home_gf_last5", hr.get("gf_last5"))
            ctx.setdefault("home_ga_last5", hr.get("ga_last5"))
        if isinstance(ar, dict):
            ctx.setdefault("away_pts_last5", ar.get("pts_last5"))
            ctx.setdefault("away_gf_last5", ar.get("gf_last5"))
            ctx.setdefault("away_ga_last5", ar.get("ga_last5"))

    def _load_alpha_table(self) -> dict[str, Any] | None:
        try:
            p = Path(str(getattr(settings, "calibration_alpha_path", "data/calibration_alpha.json")))
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_backtest_metrics(self) -> dict[str, Any] | None:
        try:
            p = Path(str(getattr(settings, "backtest_metrics_path", "data/backtest_metrics.json")))
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_decision_gate_tuned(self) -> dict[str, Any] | None:
        if not bool(getattr(settings, "decision_gate_tuning_enabled", True)):
            return None
        p = Path(str(getattr(settings, "decision_gate_tuned_path", "data/decision_gate_tuned.json")))
        try:
            st = p.stat()
        except Exception:
            return None
        try:
            mtime_ns = int(st.st_mtime_ns)
        except Exception:
            mtime_ns = None
        if self._decision_gate_tuned_cache is not None and mtime_ns is not None and self._decision_gate_tuned_mtime_ns == mtime_ns:
            return self._decision_gate_tuned_cache
        th = load_tuned_thresholds(str(p))
        if isinstance(th, dict) and th:
            data = {"thresholds": th}
            self._decision_gate_tuned_cache = data
            self._decision_gate_tuned_mtime_ns = mtime_ns
            return data
        return None

    def _decision_gate_cfg(self) -> dict[str, Any] | None:
        tuned = self._load_decision_gate_tuned()
        if isinstance(tuned, dict):
            th = tuned.get("thresholds")
            if isinstance(th, dict) and th:
                return tuned
        return getattr(settings, "decision_gate_thresholds", None)

    def _apply_inseason_alpha(self, *, championship: str, ctx: dict[str, Any]) -> None:
        cal = ctx.get("calibration")
        if isinstance(cal, dict) and "alpha" in cal:
            return

        data = self._load_alpha_table()
        if not isinstance(data, dict):
            return
        champs = data.get("championships")
        if not isinstance(champs, dict):
            return
        row = champs.get(str(championship))
        if not isinstance(row, dict):
            return
        try:
            a = float(row.get("alpha", 0.0) or 0.0)
        except Exception:
            a = 0.0

        ctx["calibration"] = {"alpha": float(a), "source": "inseason_alpha"}

    def _ttl_seconds(self, *, status: str, kickoff_unix: float | None, context: dict[str, Any]) -> int:
        if str(status or "").upper() == "LIVE":
            return 0
        now = datetime.now(timezone.utc).timestamp()
        ttl = 6 * 3600
        if isinstance(kickoff_unix, (int, float)):
            dt = float(kickoff_unix) - float(now)
            if dt <= 0:
                ttl = min(ttl, 60 * 60)
            elif dt <= 2 * 3600:
                ttl = min(ttl, 60 * 60)
            elif dt <= 10 * 3600:
                ttl = min(ttl, 2 * 3600)
        lineup = context.get("lineup_confirmed")
        if bool(lineup):
            ttl = min(ttl, 60 * 60)
        return int(ttl)

    def _norm_team(self, name: Any) -> str:
        s = str(name or "").strip()
        s = " ".join(s.split())
        if len(s) > 80:
            s = s[:80]
        return s
    
    def _resolve_team(self, *, championship: str, name: Any) -> str:
        s = self._norm_team(name)
        if not s:
            return s
        r = self._team_resolver
        if r is None:
            return s
        try:
            res = r.resolve(championship=str(championship), name=str(s))
        except Exception:
            return s
        out = str(res.resolved or "").strip()
        return out or s

    def predict_match(
        self,
        *,
        championship: str,
        match_id: str | None = None,
        home_team: str,
        away_team: str,
        status: str,
        kickoff_unix: float | None = None,
        context: dict[str, Any],
    ) -> PredictionResult:
        ctx = dict(context or {})
        ctx["real_data_only"] = settings.real_data_only
        self._apply_kickoff_context(kickoff_unix=kickoff_unix, ctx=ctx)
        self._apply_inseason_alpha(championship=str(championship), ctx=ctx)
        tl = time_left_ms()
        deadline_low = tl is not None and tl <= 150
        if tl is not None and tl <= 30:
            probs = {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
            explain = {"degradation_level": 3, "warnings": ["deadline_low"], "safe_mode": True, "safe_mode_reason": "deadline_low"}
            explain["chaos"] = {"index": 0.0, "upset_watch": False, "flags": [], "inputs": {"available": False}}
            cfg = self._decision_gate_cfg()
            explain["decision_gate_config"] = "tuned" if isinstance(cfg, dict) and isinstance(cfg.get("thresholds"), dict) else "static"
            th0 = select_thresholds(str(championship), cfg)

            chaos_index = None
            if isinstance(explain.get("chaos"), dict):
                try:
                    chaos_index = float(explain["chaos"].get("index"))
                except Exception:
                    chaos_index = None

            th = th0
            adj = None
            if isinstance(chaos_index, (int, float)):
                th, adj = adjust_thresholds_for_chaos(th0, float(chaos_index))
            if adj:
                explain["decision_gate_adjustments"] = {"chaos": adj}

            explain["decision_gate"] = evaluate_decision(championship=str(championship), probs=probs, confidence=float(0.0), thresholds=th)
            return PredictionResult(probabilities=probs, explain=explain, confidence=0.0, ranges=None)

        rh = self._team_resolver.resolve(championship=str(championship), name=str(home_team))
        ra = self._team_resolver.resolve(championship=str(championship), name=str(away_team))
        team_name_resolution = {
            "home": {"raw": rh.raw, "resolved": rh.resolved, "method": rh.method, "canonical": rh.canonical, "score": rh.score},
            "away": {"raw": ra.raw, "resolved": ra.resolved, "method": ra.method, "canonical": ra.canonical, "score": ra.score},
        }
        home_team_n = rh.resolved
        away_team_n = ra.resolved
        # arricchimento automatico context (stagionalità)
        self._apply_time_context(ctx=ctx, kickoff_unix=float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None)

        # rest-days reali (da team_dynamics.json)
        self._apply_rest_from_team_dynamics(
            championship=str(championship),
            home_team=str(home_team_n),
            away_team=str(away_team_n),
            kickoff_unix=kickoff_unix,
            ctx=ctx,
        )
        self._apply_form_context(championship=str(championship), home_team=home_team_n, away_team=away_team_n, ctx=ctx)
        match_key = str(match_id or f"{championship}|{home_team_n}|{away_team_n}").strip()
        if len(match_key) > 160:
            match_key = match_key[:160]

        cache_key: str | None = None
        cache_hit = False
        cached_payload: dict[str, Any] | None = None
        cache = None
        try:
            cache = SqliteCache(db_path=cache_db_path())
        except Exception:
            cache = None
        cache_disabled = cache is None or deadline_low

        model_v = self._artifact_version(artifact_dir() / f"model_1x2_{championship}.joblib")
        calib_v = self._artifact_version(artifact_dir() / f"calibrator_1x2_{championship}.joblib")
        feature_v = str(ctx.get("feature_version") or FEATURE_VERSION)
        ratings_path = Path(str(getattr(settings, "ratings_path", "") or ""))
        ratings_v = self._artifact_version(ratings_path) if str(ratings_path) else "missing"
        alpha = 0.0
        calibration = ctx.get("calibration")
        if isinstance(calibration, dict):
            try:
                alpha = float(calibration.get("alpha", 0.0) or 0.0)
            except Exception:
                alpha = 0.0
        inputs_hash = stable_json_hash(
            {
                "home_team": str(home_team_n),
                "away_team": str(away_team_n),
                "status": str(status),
                "matchday": ctx.get("matchday"),
                "kickoff_unix": float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None,
                "ratings_v": str(ratings_v),
                "alpha": float(alpha),
                "weather": ctx.get("weather") if isinstance(ctx.get("weather"), dict) else None,
            }
        )
        cache_key = build_cache_key(
            championship=str(championship),
            match_id=match_key,
            model_version=str(model_v),
            feature_version=str(feature_v),
            calibrator_version=str(calib_v),
            inputs_hash=str(inputs_hash),
        )

        if cache is not None and not cache_disabled:
            try:
                hit = cache.get(cache_key=str(cache_key))
            except Exception:
                hit = None
            if hit is not None and isinstance(hit.payload, dict):
                cached_payload = dict(hit.payload)
                cache_hit = True
            elif hit is None:
                cache_hit = False

        if cached_payload is not None:
            probs0 = cached_payload.get("probabilities")
            explain0 = cached_payload.get("explain")
            conf0 = cached_payload.get("confidence")
            ranges0 = cached_payload.get("ranges")
            probs = dict(probs0) if isinstance(probs0, dict) else {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
            explain = dict(explain0) if isinstance(explain0, dict) else {}
            deg = build_degradation(cache_disabled=False, calibration_disabled=False, deadline_low=deadline_low)
            explain["degradation_level"] = int(deg.level)
            explain["warnings"] = list(deg.warnings)
            explain["cache"] = {"hit": True, "key": str(cache_key)}
            explain["team_name_resolution"] = team_name_resolution
            chaos = compute_chaos(
                team_dynamics_payload=self._load_team_dynamics(),
                championship=str(championship),
                home_team=str(home_team_n),
                away_team=str(away_team_n),
                kickoff_unix=float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None,
                best_prob=max(probs.values()) if isinstance(probs, dict) and probs else None,
            )
            if isinstance(chaos, dict):
                explain["chaos"] = chaos
            cfg = self._decision_gate_cfg()
            explain["decision_gate_config"] = "tuned" if isinstance(cfg, dict) and isinstance(cfg.get("thresholds"), dict) else "static"
            th0 = select_thresholds(str(championship), cfg)

            chaos_index = None
            if isinstance(explain.get("chaos"), dict):
                try:
                    chaos_index = float(explain["chaos"].get("index"))
                except Exception:
                    chaos_index = None

            th = th0
            adj = None
            if isinstance(chaos_index, (int, float)):
                th, adj = adjust_thresholds_for_chaos(th0, float(chaos_index))
            if adj:
                explain["decision_gate_adjustments"] = {"chaos": adj}

            explain["decision_gate"] = evaluate_decision(
                championship=str(championship),
                probs=probs,
                confidence=float(conf0 or 0.0),
                thresholds=th,
            )
            try:
                data = self._load_backtest_metrics()
                if isinstance(data, dict):
                    champs0 = data.get("championships")
                    champs = champs0 if isinstance(champs0, dict) else data.get("leagues")
                    if isinstance(champs, dict):
                        row = champs.get(str(championship))
                        if isinstance(row, dict):
                            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                            explain["backtest_metrics"] = {
                                "n": row.get("n"),
                                "accuracy": row.get("accuracy"),
                                "brier": row.get("brier"),
                                "logloss": row.get("logloss") if row.get("logloss") is not None else row.get("log_loss"),
                                "ece": row.get("ece"),
                                "lookback_days": meta.get("lookback_days"),
                            }
            except Exception:
                pass
            return PredictionResult(
                probabilities=probs,
                explain=explain,
                confidence=float(conf0) if isinstance(conf0, (int, float)) else None,
                ranges=dict(ranges0) if isinstance(ranges0, dict) else None,
            )

        raw = self._ensemble.predict(championship=championship, home_team=home_team_n, away_team=away_team_n, status=status, context=ctx)

        probs = dict(raw["probabilities"])
        s = sum(max(v, 0.0) for v in probs.values())
        if s <= 0:
            probs = {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
        else:
            probs = {k: max(v, 0.0) / s for k, v in probs.items()}

        for k, v in list(probs.items()):
            probs[k] = min(max(v, 1e-6), 1.0)

        s = sum(probs.values())
        probs = {k: v / s for k, v in probs.items()} if s > 0 else probs

        # --- Temperature calibration (per league)
        temp_applied = False
        temp_T = None
        temp_n = None

        if bool(getattr(settings, "calibration_temperature_enabled", True)):
            temp_data = self._load_json_cached(
                str(getattr(settings, "calibration_temperature_path", "data/calibration_temperature.json")),
                "_temperature_cache",
                "_temperature_mtime_ns",
            )
            try:
                champ_row = (temp_data or {}).get("championships", {}).get(str(championship))
                if isinstance(champ_row, dict):
                    temp_T = float(champ_row.get("temperature", 1.0))
                    temp_n = int(champ_row.get("n", 0))
                    if temp_T and temp_T != 1.0:
                        probs = apply_temperature(probs, temp_T)
                        temp_applied = True
            except Exception:
                pass

        # --- Drift boost (se drift high, rendi più conservativo)
        drift_level = None
        drift_flags = []
        extra_alpha = 0.0

        if bool(getattr(settings, "drift_monitor_enabled", True)):
            drift_data = self._load_json_cached(
                str(getattr(settings, "drift_status_path", "data/drift_status.json")),
                "_drift_cache",
                "_drift_mtime_ns",
            )
            champ_row = (drift_data or {}).get("championships", {}).get(str(championship))
            if isinstance(champ_row, dict):
                drift_level = champ_row.get("level")
                drift_flags = champ_row.get("flags") or []
                if drift_level == "high":
                    extra_alpha = 0.06  # boost conservativo
                elif drift_level == "warn":
                    extra_alpha = 0.03

        conf = raw.get("confidence_score")
        if not isinstance(conf, (int, float)):
            conf = None
        ranges = raw.get("ranges")
        if not isinstance(ranges, dict):
            ranges = None

        explain = dict(raw.get("explain", {})) if isinstance(raw.get("explain", {}), dict) else {}
        ec = explain.get("ensemble_components") if isinstance(explain, dict) else None
        calibrated = False
        if isinstance(ec, dict):
            calibrated = bool(ec.get("calibrated"))
        calibration_disabled = False
        if calib_v == "missing":
            calibration_disabled = True
        
        # Apply drift boost to alpha if needed
        alpha_with_drift = float(alpha or 0.0) + float(extra_alpha or 0.0)
        if alpha_with_drift > 0.35:
            alpha_with_drift = 0.35
        
        if not calibrated and not deadline_low:
            probs = self._calibrate_probs(probs, alpha_with_drift)
            explain.setdefault("calibration", {})
            explain["calibration"].update({
                "alpha": float(alpha), 
                "alpha_applied": bool(alpha > 0.0),
                "drift_boost": float(extra_alpha),
                "alpha_total": float(alpha_with_drift)
            })
            explain["calibration"]["temperature"] = {
                "applied": bool(temp_applied),
                "T": float(temp_T) if temp_T is not None else None,
                "n": int(temp_n) if temp_n is not None else None,
            }
            explain.setdefault("drift", {})
            explain["drift"] = {
                "level": drift_level,
                "flags": drift_flags,
                "extra_alpha": float(extra_alpha),
            }
        elif not calibrated and deadline_low:
            calibration_disabled = True

        explain["versions"] = {"model": str(model_v), "calibrator": str(calib_v), "feature": str(feature_v), "ratings": str(ratings_v)}
        if cache_key is not None:
            explain["cache"] = {"hit": False, "key": str(cache_key)}
        deg = build_degradation(cache_disabled=cache_disabled, calibration_disabled=calibration_disabled, deadline_low=deadline_low)
        explain["degradation_level"] = int(deg.level)
        explain["warnings"] = list(deg.warnings)
        explain["team_name_resolution"] = team_name_resolution
        chaos = compute_chaos(
            team_dynamics_payload=self._load_team_dynamics(),
            championship=str(championship),
            home_team=str(home_team_n),
            away_team=str(away_team_n),
            kickoff_unix=float(kickoff_unix) if isinstance(kickoff_unix, (int, float)) else None,
            best_prob=max(probs.values()) if isinstance(probs, dict) and probs else None,
        )
        if isinstance(chaos, dict):
            explain["chaos"] = chaos
        if bool(getattr(settings, "decision_gate_enabled", True)):
            try:
                cfg = self._decision_gate_cfg()
                explain["decision_gate_config"] = "tuned" if isinstance(cfg, dict) and isinstance(cfg.get("thresholds"), dict) else "static"
                th0 = select_thresholds(str(championship), cfg)

                chaos_index = None
                if isinstance(explain.get("chaos"), dict):
                    try:
                        chaos_index = float(explain["chaos"].get("index"))
                    except Exception:
                        chaos_index = None

                th = th0
                adj = None
                if isinstance(chaos_index, (int, float)):
                    th, adj = adjust_thresholds_for_chaos(th0, float(chaos_index))
                if adj:
                    explain["decision_gate_adjustments"] = {"chaos": adj}

                decision = evaluate_decision(
                    championship=str(championship),
                    probs=probs,
                    confidence=float(conf or 0.0),
                    thresholds=th,
                )
                explain["decision"] = decision
            except Exception:
                pass

        try:
            data = self._load_backtest_metrics()
            if isinstance(data, dict):
                champs0 = data.get("championships")
                champs = champs0 if isinstance(champs0, dict) else data.get("leagues")
                if isinstance(champs, dict):
                    row = champs.get(str(championship))
                    if isinstance(row, dict):
                        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                        explain["backtest_metrics"] = {
                            "n": row.get("n"),
                            "accuracy": row.get("accuracy"),
                            "brier": row.get("brier"),
                            "logloss": row.get("logloss") if row.get("logloss") is not None else row.get("log_loss"),
                            "ece": row.get("ece"),
                            "lookback_days": meta.get("lookback_days"),
                        }
        except Exception:
            pass

        out = PredictionResult(probabilities=probs, explain=explain, confidence=float(conf) if conf is not None else None, ranges=ranges)

        if cache is not None and cache_key is not None and not cache_disabled:
            ttl = self._ttl_seconds(status=status, kickoff_unix=kickoff_unix, context=ctx)
            if ttl > 0:
                to_cache = {"probabilities": dict(out.probabilities), "explain": {k: v for k, v in out.explain.items() if k != "cache"}, "confidence": out.confidence, "ranges": out.ranges}
                try:
                    cache.set(
                        cache_key=str(cache_key),
                        championship=str(championship),
                        match_id=str(match_key),
                        matchday=int(ctx.get("matchday")) if isinstance(ctx.get("matchday"), int) else None,
                        payload=to_cache,
                        ttl_seconds=int(ttl),
                        model_version=str(model_v),
                        feature_version=str(feature_v),
                        calibrator_version=str(calib_v),
                        inputs_hash=str(inputs_hash),
                    )
                except Exception:
                    pass

        return out
