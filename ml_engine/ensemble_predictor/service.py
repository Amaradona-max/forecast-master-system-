from __future__ import annotations

import hashlib
from typing import Any

from ml_engine.dixon_coles_enhanced import dixon_coles_1x2
from ml_engine.poisson_goal_model import match_probabilities
from ml_engine.performance_targets import CHAMPIONSHIP_TARGETS
from ml_engine.team_ratings_store import get_team_strength


class EnsemblePredictorService:
    def predict(self, *, championship: str, home_team: str, away_team: str, status: str, context: dict[str, Any]) -> dict[str, Any]:
        real_only = bool(context.get("real_data_only"))
        home_lookup = get_team_strength(championship=championship, team=home_team)
        away_lookup = get_team_strength(championship=championship, team=away_team)
        missing_home = home_lookup is None
        missing_away = away_lookup is None

        if real_only:
            home_base = home_lookup.strength if home_lookup is not None else 0.0
            away_base = away_lookup.strength if away_lookup is not None else 0.0
        else:
            home_base = home_lookup.strength if home_lookup is not None else _team_strength(home_team)
            away_base = away_lookup.strength if away_lookup is not None else _team_strength(away_team)
        target = CHAMPIONSHIP_TARGETS.get(championship, {})
        home_adv = float(target.get("home_advantage", 0.12))
        pace = float(target.get("pace_intensity", 0.0))
        weather_impact = float(target.get("weather_impact", 0.0))
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
        dc = dixon_coles_1x2(lam_home=lam_home, lam_away=lam_away, rho=0.08)

        if status == "LIVE":
            w_base, w_poi, w_dc = 0.20, 0.50, 0.30
        else:
            w_base, w_poi, w_dc = 0.40, 0.35, 0.25

        p_home = (w_base * p_home_base) + (w_poi * float(poisson["1x2"]["home_win"])) + (w_dc * float(dc["home_win"]))
        p_draw = (w_base * p_draw_base) + (w_poi * float(poisson["1x2"]["draw"])) + (w_dc * float(dc["draw"]))
        p_away = (w_base * p_away_base) + (w_poi * float(poisson["1x2"]["away_win"])) + (w_dc * float(dc["away_win"]))
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

        explain = {
            "championship_key_features": list(target.get("key_features", [])),
            "components": {
                "team_strength_delta": float(home_base - away_base),
                "team_strength_source": "elo"
                if (not missing_home and not missing_away)
                else ("elo_baseline" if real_only else "hash"),
                "ratings_missing_home": bool(missing_home),
                "ratings_missing_away": bool(missing_away),
                "home_advantage": home_adv,
                "pace_intensity": pace,
                "weather_factor": weather_factor,
                "status": status,
                "lam_home": float(lam_home),
                "lam_away": float(lam_away),
            },
            "derived_markets": {
                "over_2_5": float(poisson["goals"]["over_2_5"]),
                "btts": float(poisson["goals"]["btts"]),
            },
            "target_accuracy_range": target.get("accuracy_target"),
        }
        if home_lookup is not None or away_lookup is not None:
            meta0: dict[str, Any] = {}
            if home_lookup is not None:
                meta0.update(dict(home_lookup.meta))
            elif away_lookup is not None:
                meta0.update(dict(away_lookup.meta))
            explain["ratings"] = meta0

        return {
            "probabilities": {"home_win": p_home, "draw": p_draw, "away_win": p_away},
            "explain": explain,
        }


def _team_strength(team: str) -> float:
    h = hashlib.sha256(team.strip().lower().encode("utf-8")).digest()
    v = int.from_bytes(h[:4], "big") / 2**32
    return (v - 0.5) * 0.9


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
