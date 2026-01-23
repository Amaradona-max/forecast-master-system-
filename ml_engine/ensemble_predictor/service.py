from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ml_engine.calibration_1x2 import calibrate_1x2
from ml_engine.dixon_coles_enhanced import dixon_coles_1x2
from ml_engine.features.builder import build_features_1x2
from ml_engine.logit_1x2_runtime import predict_1x2
from ml_engine.poisson_goal_model import match_probabilities
from ml_engine.performance_targets import CHAMPIONSHIP_TARGETS
from ml_engine.safety.safe_mode import get_safe_mode
from ml_engine.team_ratings_store import get_team_strength
from ml_engine.team_setpiece_store import get_team_setpieces
from ml_engine.team_territory_store import get_team_territory
from ml_engine.config import monitoring_dir


class EnsemblePredictorService:
    def predict(self, *, championship: str, home_team: str, away_team: str, status: str, context: dict[str, Any]) -> dict[str, Any]:
        home_lookup = get_team_strength(championship=championship, team=home_team)
        away_lookup = get_team_strength(championship=championship, team=away_team)
        missing_home = home_lookup is None
        missing_away = away_lookup is None

        home_base = home_lookup.strength if home_lookup is not None else 0.0
        away_base = away_lookup.strength if away_lookup is not None else 0.0
        target = CHAMPIONSHIP_TARGETS.get(championship, {})
        home_adv = float(target.get("home_advantage", 0.12))
        pace = float(target.get("pace_intensity", 0.0))
        weather_impact = float(target.get("weather_impact", 0.0))
        rho = float(target.get("dixon_coles_rho", 0.08))
        live_bias = 0.0 if status != "LIVE" else 0.03

        weather = context.get("weather", {})
        weather_factor = 0.0
        if isinstance(weather, dict):
            wind = float(weather.get("wind_kmh", 0.0) or 0.0)
            rain = float(weather.get("rain_mm", 0.0) or 0.0)
            weather_factor = -weather_impact * (0.003 * wind + 0.006 * rain)

        x = (home_base - away_base) + home_adv + live_bias + weather_factor + 0.02 * pace
        p_home_base, p_draw_base, p_away_base = _softmax3(x, 0.0, -x)

        lam_home, lam_away = _expected_goals(
            home_base=home_base,
            away_base=away_base,
            home_adv=home_adv,
            pace=pace,
            weather_factor=weather_factor,
        )

        poisson = match_probabilities(lam_home=lam_home, lam_away=lam_away)
        dc = dixon_coles_1x2(lam_home=lam_home, lam_away=lam_away, rho=rho)

        matchday = context.get("matchday")
        md: int | None = int(matchday) if isinstance(matchday, int) else None
        safe = get_safe_mode(championship)

        if status == "LIVE":
            w_base, w_poi, w_dc, w_logit = 0.20, 0.50, 0.25, 0.05
        else:
            if md is None:
                w_base, w_poi, w_dc, w_logit = 0.35, 0.32, 0.23, 0.10
            elif md <= 6:
                w_base, w_poi, w_dc, w_logit = 0.25, 0.25, 0.20, 0.30
            elif md >= 12:
                w_base, w_poi, w_dc, w_logit = 0.30, 0.35, 0.25, 0.10
            else:
                t = (md - 6) / 6.0
                w_logit = (1.0 - t) * 0.30 + t * 0.10
                w_base = (1.0 - t) * 0.25 + t * 0.30
                w_poi = (1.0 - t) * 0.25 + t * 0.35
                w_dc = (1.0 - t) * 0.20 + t * 0.25

        home_elo = home_lookup.meta.get("elo") if home_lookup is not None else None
        away_elo = away_lookup.meta.get("elo") if away_lookup is not None else None
        logit_features, missing_flags, feature_version = build_features_1x2(home_elo=home_elo, away_elo=away_elo, context=context)

        logit = predict_1x2(championship=championship, features=logit_features)
        logit_available = isinstance(logit, dict)
        if not logit_available:
            w_logit = 0.0
            s_w = w_base + w_poi + w_dc
            if s_w > 0:
                w_base, w_poi, w_dc = w_base / s_w, w_poi / s_w, w_dc / s_w

        p_home = (w_base * p_home_base) + (w_poi * float(poisson["1x2"]["home_win"])) + (w_dc * float(dc["home_win"]))
        p_draw = (w_base * p_draw_base) + (w_poi * float(poisson["1x2"]["draw"])) + (w_dc * float(dc["draw"]))
        p_away = (w_base * p_away_base) + (w_poi * float(poisson["1x2"]["away_win"])) + (w_dc * float(dc["away_win"]))
        if logit_available:
            p_home += w_logit * float(logit.get("home_win", 0.0))
            p_draw += w_logit * float(logit.get("draw", 0.0))
            p_away += w_logit * float(logit.get("away_win", 0.0))
        p_home, p_draw, p_away = _normalize3(p_home, p_draw, p_away)

        events = context.get("events", [])
        if status == "LIVE" and isinstance(events, list):
            goal_delta = sum(1 for e in events if isinstance(e, dict) and e.get("type") == "goal")
            if goal_delta > 0:
                p_home = min(p_home + 0.02 * goal_delta, 0.92)
                p_away = max(p_away - 0.015 * goal_delta, 0.02)
                p_draw = 1.0 - (p_home + p_away)
                if p_draw < 0.02:
                    p_draw = 0.02
                    s = p_home + p_draw + p_away
                    p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s

        base_comp = {"home_win": p_home_base, "draw": p_draw_base, "away_win": p_away_base}
        poi_comp = {
            "home_win": float(poisson["1x2"]["home_win"]),
            "draw": float(poisson["1x2"]["draw"]),
            "away_win": float(poisson["1x2"]["away_win"]),
        }
        dc_comp = {"home_win": float(dc["home_win"]), "draw": float(dc["draw"]), "away_win": float(dc["away_win"])}
        logit_comp = logit if logit_available else None

        probs0 = {"home_win": p_home, "draw": p_draw, "away_win": p_away}
        probs1, calibrated = calibrate_1x2(championship=championship, probs=probs0)
        p_home = float(probs1.get("home_win", 0.0) or 0.0)
        p_draw = float(probs1.get("draw", 0.0) or 0.0)
        p_away = float(probs1.get("away_win", 0.0) or 0.0)

        shrink = 0.0
        missing_count = (1 if missing_home else 0) + (1 if missing_away else 0)
        if missing_count == 2:
            shrink = 0.85
        elif missing_count == 1:
            shrink = 0.75
        if md is not None and status != "LIVE":
            m_cap = int(target.get("early_season_matchday_cap", 12) or 12)
            if m_cap < 6:
                m_cap = 6
            early_bonus = _clamp((float(m_cap) - float(md)) / float(m_cap), 0.0, 1.0) * 0.05
            shrink = _clamp(shrink + early_bonus, 0.0, 0.95)
        if bool(safe.enabled) and shrink < 0.40:
            shrink = _clamp(shrink + 0.08, 0.0, 0.40)
        if shrink > 0:
            u = 1.0 / 3.0
            p_home = (1.0 - shrink) * p_home + shrink * u
            p_draw = (1.0 - shrink) * p_draw + shrink * u
            p_away = (1.0 - shrink) * p_away + shrink * u
            p_home, p_draw, p_away = _normalize3(p_home, p_draw, p_away)

        territory_explain: dict[str, Any] | None = None
        home_tpx = get_team_territory(championship=championship, team=home_team)
        away_tpx = get_team_territory(championship=championship, team=away_team)
        if home_tpx is not None and away_tpx is not None and status != "LIVE":
            home_edge = (float(home_tpx.off_index) - float(away_tpx.def_index)) / 100.0
            away_edge = (float(away_tpx.off_index) - float(home_tpx.def_index)) / 100.0
            net = float(home_edge - away_edge)
            factor = 0.01 if not bool(safe.enabled) else 0.006
            raw_shift = _clamp(net * factor, -0.02, 0.02)
            floor = 0.02
            shift = raw_shift
            if shift > 0:
                shift = min(float(shift), float(p_away) - floor)
            elif shift < 0:
                shift = max(float(shift), floor - float(p_home))
            p_home = float(p_home) + float(shift)
            p_away = float(p_away) - float(shift)
            p_home, p_draw, p_away = _normalize3(float(p_home), float(p_draw), float(p_away))

            advantage = "none"
            if abs(net) >= 0.12:
                advantage = "home" if net > 0 else "away"
            territory_explain = {
                "available": True,
                "advantage": advantage,
                "home": {"off_index": float(home_tpx.off_index), "def_index": float(home_tpx.def_index)},
                "away": {"off_index": float(away_tpx.off_index), "def_index": float(away_tpx.def_index)},
                "edges": {"home_vs_away_def": float(home_edge), "away_vs_home_def": float(away_edge), "net": float(net)},
                "shift_applied": float(shift),
            }
        else:
            territory_explain = {"available": False}

        setpiece_explain: dict[str, Any] | None = None
        sp_home = get_team_setpieces(championship=championship, team=home_team)
        sp_away = get_team_setpieces(championship=championship, team=away_team)
        if sp_home is not None and sp_away is not None and status != "LIVE":
            home_edge = (float(sp_home.off_index) - float(sp_away.def_index)) / 100.0
            away_edge = (float(sp_away.off_index) - float(sp_home.def_index)) / 100.0
            delta0 = float(home_edge - away_edge)

            max_shift = 0.03
            delta = _clamp(float(delta0) * 0.02, -float(max_shift), float(max_shift))

            probs2 = _shift_home_away({"home_win": float(p_home), "draw": float(p_draw), "away_win": float(p_away)}, delta)
            p_home = float(probs2.get("home_win", 0.0) or 0.0)
            p_draw = float(probs2.get("draw", 0.0) or 0.0)
            p_away = float(probs2.get("away_win", 0.0) or 0.0)

            setpiece_explain = {
                "available": True,
                "home_off": float(sp_home.off_index),
                "home_def": float(sp_home.def_index),
                "away_off": float(sp_away.off_index),
                "away_def": float(sp_away.def_index),
                "home_edge": round(float(home_edge), 4),
                "away_edge": round(float(away_edge), 4),
                "delta_applied": round(float(delta), 4),
                "mismatch": bool(abs(float(home_edge - away_edge)) >= 0.25),
                "home": {"off_index": float(sp_home.off_index), "def_index": float(sp_home.def_index)},
                "away": {"off_index": float(sp_away.off_index), "def_index": float(sp_away.def_index)},
            }
        else:
            setpiece_explain = {"available": False}

        p_home, p_draw, p_away = _apply_guardrails(p_home, p_draw, p_away)

        var_ensemble = _ensemble_variance(base=base_comp, poisson=poi_comp, dixon_coles=dc_comp, logit=logit_comp)
        data_quality = 1.0
        if missing_count == 1:
            data_quality *= 0.85
        elif missing_count == 2:
            data_quality *= 0.70
        if md is None:
            data_quality *= 0.85
        if not logit_available:
            data_quality *= 0.90
        margin = _margin({"home_win": p_home, "draw": p_draw, "away_win": p_away})
        confidence_raw = margin * (1.0 - var_ensemble) * data_quality
        confidence_score = _clamp(confidence_raw / 0.60, 0.0, 1.0)
        hi_thr, med_thr = _confidence_thresholds(championship=championship)
        if confidence_score >= hi_thr:
            confidence_label = "HIGH"
        elif confidence_score >= med_thr:
            confidence_label = "MEDIUM"
        else:
            confidence_label = "LOW"
        if bool(safe.enabled) and confidence_label == "HIGH":
            confidence_label = "MEDIUM"

        ranges = _probability_ranges(
            probs={"home_win": p_home, "draw": p_draw, "away_win": p_away},
            var_ensemble=var_ensemble,
            data_quality=data_quality,
        )
        if bool(safe.enabled):
            ranges = _widen_ranges(probs={"home_win": p_home, "draw": p_draw, "away_win": p_away}, ranges=ranges, factor=1.15)

        explain = {
            "feature_version": str(feature_version),
            "missing_flags": dict(missing_flags),
            "safe_mode": bool(safe.enabled),
            "safe_mode_reason": safe.reason,
            "championship_key_features": list(target.get("key_features", [])),
            "components": {
                "team_strength_delta": float(home_base - away_base),
                "team_strength_source": "elo" if (not missing_home and not missing_away) else "neutral_missing",
                "ratings_missing_home": bool(missing_home),
                "ratings_missing_away": bool(missing_away),
                "home_advantage": home_adv,
                "pace_intensity": pace,
                "weather_factor": weather_factor,
                "status": status,
                "lam_home": float(lam_home),
                "lam_away": float(lam_away),
                "probability_shrinkage": float(shrink),
                "dixon_coles_rho": float(rho),
            },
            "ensemble_components": {
                "base": base_comp,
                "poisson": poi_comp,
                "dixon_coles": dc_comp,
                "logit": logit_comp,
                "logit_available": bool(logit_available),
                "calibrated": bool(calibrated),
            },
            "derived_markets": {
                "over_2_5": float(poisson["goals"]["over_2_5"]),
                "btts": float(poisson["goals"]["btts"]),
            },
            "target_accuracy_range": target.get("accuracy_target"),
            "confidence": {"score": float(confidence_score), "label": str(confidence_label)},
            "ranges": ranges,
        }
        if isinstance(territory_explain, dict):
            explain["territory"] = territory_explain
        if isinstance(setpiece_explain, dict):
            explain["set_pieces"] = setpiece_explain
        if home_lookup is not None or away_lookup is not None:
            meta0: dict[str, Any] = {}
            if home_lookup is not None:
                meta0.update(dict(home_lookup.meta))
            elif away_lookup is not None:
                meta0.update(dict(away_lookup.meta))
            explain["ratings"] = meta0
        if home_tpx is not None or away_tpx is not None:
            meta1: dict[str, Any] = {}
            if home_tpx is not None:
                meta1.update(dict(home_tpx.meta))
            elif away_tpx is not None:
                meta1.update(dict(away_tpx.meta))
            explain["territory_meta"] = meta1
        if sp_home is not None or sp_away is not None:
            meta2: dict[str, Any] = {}
            if sp_home is not None:
                meta2.update(dict(sp_home.meta))
            elif sp_away is not None:
                meta2.update(dict(sp_away.meta))
            explain["setpiece_meta"] = meta2

        return {
            "probabilities": {"home_win": p_home, "draw": p_draw, "away_win": p_away},
            "ranges": ranges,
            "confidence": {"score": float(confidence_score), "label": str(confidence_label)},
            "confidence_score": float(confidence_score),
            "confidence_label": str(confidence_label),
            "feature_version": str(feature_version),
            "safe_mode": bool(safe.enabled),
            "safe_mode_reason": safe.reason,
            "explain": explain,
        }


def _softmax3(a: float, b: float, c: float) -> tuple[float, float, float]:
    m = max(a, b, c)
    ea, eb, ec = _exp(a - m), _exp(b - m), _exp(c - m)
    s = ea + eb + ec
    return ea / s, eb / s, ec / s


def _exp(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        x = 60
    import math

    return math.exp(x)


def _expected_goals(*, home_base: float, away_base: float, home_adv: float, pace: float, weather_factor: float) -> tuple[float, float]:
    lam_home = 1.35 + (0.75 * home_base) - (0.55 * away_base) + (0.30 * home_adv) + (0.15 * pace) + weather_factor
    lam_away = 1.05 + (0.70 * away_base) - (0.50 * home_base) + (0.05 * pace) + weather_factor
    return _clamp(lam_home, 0.20, 4.00), _clamp(lam_away, 0.20, 4.00)


def _normalize3(a: float, b: float, c: float) -> tuple[float, float, float]:
    a = max(a, 0.0)
    b = max(b, 0.0)
    c = max(c, 0.0)
    s = a + b + c
    if s <= 0:
        return 1 / 3, 1 / 3, 1 / 3
    return a / s, b / s, c / s


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _apply_guardrails(p_home: float, p_draw: float, p_away: float) -> tuple[float, float, float]:
    try:
        p_home = float(p_home)
        p_draw = float(p_draw)
        p_away = float(p_away)
    except Exception:
        return (1 / 3, 1 / 3, 1 / 3)
    if not (math.isfinite(p_home) and math.isfinite(p_draw) and math.isfinite(p_away)):
        return (1 / 3, 1 / 3, 1 / 3)

    p_home = _clamp(p_home, 0.03, 0.90)
    p_draw = _clamp(p_draw, 0.03, 0.90)
    p_away = _clamp(p_away, 0.03, 0.90)
    p_home, p_draw, p_away = _normalize3(p_home, p_draw, p_away)
    return p_home, p_draw, p_away


def _shift_home_away(probs: dict[str, float], delta: float) -> dict[str, float]:
    try:
        p_home = float(probs.get("home_win", 0.0) or 0.0)
        p_draw = float(probs.get("draw", 0.0) or 0.0)
        p_away = float(probs.get("away_win", 0.0) or 0.0)
    except Exception:
        return {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}

    floor = 0.02
    shift = float(delta)
    if shift > 0:
        shift = min(float(shift), float(p_away) - float(floor))
    elif shift < 0:
        shift = max(float(shift), float(floor) - float(p_home))

    p_home = float(p_home) + float(shift)
    p_away = float(p_away) - float(shift)
    p_home, p_draw, p_away = _normalize3(float(p_home), float(p_draw), float(p_away))
    return {"home_win": float(p_home), "draw": float(p_draw), "away_win": float(p_away)}


def _margin(probs: dict[str, float]) -> float:
    v = sorted([float(probs.get("home_win", 0.0) or 0.0), float(probs.get("draw", 0.0) or 0.0), float(probs.get("away_win", 0.0) or 0.0)], reverse=True)
    best = v[0] if v else 0.0
    second = v[1] if len(v) > 1 else 0.0
    return _clamp(best - second, 0.0, 1.0)


def _ensemble_variance(*, base: dict[str, float], poisson: dict[str, float], dixon_coles: dict[str, float], logit: dict[str, float] | None) -> float:
    comps: list[dict[str, float]] = [base, poisson, dixon_coles]
    if isinstance(logit, dict):
        comps.append(logit)
    if len(comps) <= 1:
        return 0.0

    def var(vals: list[float]) -> float:
        m = sum(vals) / float(len(vals))
        return sum((x - m) ** 2 for x in vals) / float(len(vals))

    out_vars: list[float] = []
    for k in ("home_win", "draw", "away_win"):
        vals = [float(c.get(k, 0.0) or 0.0) for c in comps]
        out_vars.append(var(vals))
    return _clamp(sum(out_vars) / 3.0, 0.0, 1.0)


def _probability_ranges(*, probs: dict[str, float], var_ensemble: float, data_quality: float) -> dict[str, dict[str, float]]:
    vol = _clamp(float(var_ensemble) * 2.0 + (1.0 - float(data_quality)) * 0.5, 0.0, 1.0)
    k = 0.10 + 0.05 * vol

    out: dict[str, dict[str, float]] = {}
    for key in ("home_win", "draw", "away_win"):
        p = float(probs.get(key, 1 / 3) or 0.0)
        lo = _clamp(p - k * vol, 0.03, 0.90)
        hi = _clamp(p + k * vol, 0.03, 0.90)
        out[key] = {"lo": float(lo), "hi": float(hi)}
    return out


_CONF_CACHE: dict[str, Any] = {"path": None, "mtime_ns": None, "data": {}}


def _confidence_thresholds(*, championship: str) -> tuple[float, float]:
    p = Path(monitoring_dir() / f"conf_thresholds_{championship}.json")
    try:
        st = p.stat()
    except Exception:
        return 0.70, 0.40
    if _CONF_CACHE.get("path") != str(p) or _CONF_CACHE.get("mtime_ns") != st.st_mtime_ns:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            raw = None
        if isinstance(raw, dict):
            _CONF_CACHE.update({"path": str(p), "mtime_ns": st.st_mtime_ns, "data": raw})
        else:
            _CONF_CACHE.update({"path": str(p), "mtime_ns": st.st_mtime_ns, "data": {}})
    data = _CONF_CACHE.get("data")
    if not isinstance(data, dict):
        return 0.70, 0.40
    hi = data.get("high")
    med = data.get("med")
    try:
        hi_f = float(hi)
    except Exception:
        hi_f = 0.70
    try:
        med_f = float(med)
    except Exception:
        med_f = 0.40
    if hi_f < 0.05 or hi_f > 0.95:
        hi_f = 0.70
    if med_f < 0.05 or med_f > 0.95 or med_f >= hi_f:
        med_f = 0.40
    return hi_f, med_f


def _widen_ranges(*, probs: dict[str, float], ranges: dict[str, dict[str, float]], factor: float) -> dict[str, dict[str, float]]:
    f = float(factor)
    if f <= 1.0:
        return ranges
    out: dict[str, dict[str, float]] = {}
    for k in ("home_win", "draw", "away_win"):
        r = ranges.get(k, {})
        lo0 = float(r.get("lo", 0.03) or 0.03)
        hi0 = float(r.get("hi", 0.90) or 0.90)
        p = float(probs.get(k, 1 / 3) or 1 / 3)
        w = max(hi0 - lo0, 0.0) * f
        lo = _clamp(p - 0.5 * w, 0.03, 0.90)
        hi = _clamp(p + 0.5 * w, 0.03, 0.90)
        if hi < lo:
            lo, hi = hi, lo
        out[k] = {"lo": float(lo), "hi": float(hi)}
    return out
