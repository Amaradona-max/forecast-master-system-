from __future__ import annotations

import math
from typing import Any

from ml_engine.features.schema import FEATURE_COLS_1X2, FEATURE_VERSION


def _num_or_nan(v: Any) -> float:
    if isinstance(v, bool):
        return float("nan")
    if isinstance(v, (int, float)):
        x = float(v)
        return x if math.isfinite(x) else float("nan")
    return float("nan")


def build_features_1x2(*, home_elo: Any, away_elo: Any, context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bool], str]:
    feats: dict[str, Any] = {}
    missing: dict[str, bool] = {}

    h_elo = _num_or_nan(home_elo)
    a_elo = _num_or_nan(away_elo)
    feats["home_elo_pre"] = h_elo
    feats["away_elo_pre"] = a_elo
    missing["home_elo_pre"] = not math.isfinite(h_elo)
    missing["away_elo_pre"] = not math.isfinite(a_elo)
    feats["elo_diff"] = (h_elo - a_elo) if (math.isfinite(h_elo) and math.isfinite(a_elo)) else float("nan")
    missing["elo_diff"] = not math.isfinite(float(feats["elo_diff"]))

    rh = _num_or_nan(context.get("home_days_rest", context.get("rest_days_home")))
    ra = _num_or_nan(context.get("away_days_rest", context.get("rest_days_away")))
    feats["home_days_rest"] = rh
    feats["away_days_rest"] = ra
    missing["home_days_rest"] = not math.isfinite(rh)
    missing["away_days_rest"] = not math.isfinite(ra)
    feats["rest_diff"] = (rh - ra) if (math.isfinite(rh) and math.isfinite(ra)) else float("nan")
    missing["rest_diff"] = not math.isfinite(float(feats["rest_diff"]))

    for k in (
        "season_year",
        "month",
        "weekday",
        "home_pts_last5",
        "away_pts_last5",
        "home_gf_last5",
        "home_ga_last5",
        "away_gf_last5",
        "away_ga_last5",
    ):
        feats[k] = _num_or_nan(context.get(k))
        missing[k] = not math.isfinite(float(feats[k]))

    out = {k: feats.get(k, float("nan")) for k in FEATURE_COLS_1X2}
    missing_out = {k: bool(missing.get(k, True)) for k in FEATURE_COLS_1X2}
    return out, missing_out, FEATURE_VERSION

