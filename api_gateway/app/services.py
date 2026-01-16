from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml_engine.ensemble_predictor.service import EnsemblePredictorService
from ml_engine.cache.cache_keys import build_cache_key, stable_json_hash
from ml_engine.cache.sqlite_cache import SqliteCache
from ml_engine.features.schema import FEATURE_VERSION
from ml_engine.resilience.degradation import build_degradation
from ml_engine.resilience.timeouts import time_left_ms
from ml_engine.config import artifact_dir, cache_db_path
from api_gateway.app.settings import settings


@dataclass(frozen=True)
class PredictionResult:
    probabilities: dict[str, float]
    explain: dict[str, Any]
    confidence: float | None = None
    ranges: dict[str, Any] | None = None


class PredictionService:
    def __init__(self) -> None:
        self._ensemble = EnsemblePredictorService()

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
        tl = time_left_ms()
        deadline_low = tl is not None and tl <= 150
        if tl is not None and tl <= 30:
            explain = {"degradation_level": 3, "warnings": ["deadline_low"], "safe_mode": True, "safe_mode_reason": "deadline_low"}
            return PredictionResult(probabilities={"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}, explain=explain, confidence=0.0, ranges=None)

        home_team_n = self._norm_team(home_team)
        away_team_n = self._norm_team(away_team)
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
        if not calibrated and not deadline_low:
            probs = self._calibrate_probs(probs, alpha)
            explain["calibration"] = {"alpha": float(alpha), "alpha_applied": bool(alpha > 0.0)}
        elif not calibrated and deadline_low:
            calibration_disabled = True

        explain["versions"] = {"model": str(model_v), "calibrator": str(calib_v), "feature": str(feature_v), "ratings": str(ratings_v)}
        if cache_key is not None:
            explain["cache"] = {"hit": False, "key": str(cache_key)}
        deg = build_degradation(cache_disabled=cache_disabled, calibration_disabled=calibration_disabled, deadline_low=deadline_low)
        explain["degradation_level"] = int(deg.level)
        explain["warnings"] = list(deg.warnings)

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
