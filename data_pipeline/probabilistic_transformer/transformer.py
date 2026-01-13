from __future__ import annotations

from typing import Any


class ProbabilisticTransformer:
    def featurize(self, match: dict[str, Any]) -> dict[str, Any]:
        home = str(match.get("home_team", "")).strip()
        away = str(match.get("away_team", "")).strip()
        feats: dict[str, Any] = {
            "home_team": home,
            "away_team": away,
            "home_advantage": 1.0,
        }
        ctx = match.get("context", {})
        if isinstance(ctx, dict):
            feats["weather_wind_kmh"] = float(ctx.get("weather", {}).get("wind_kmh", 0.0) or 0.0) if isinstance(ctx.get("weather"), dict) else 0.0
            feats["weather_rain_mm"] = float(ctx.get("weather", {}).get("rain_mm", 0.0) or 0.0) if isinstance(ctx.get("weather"), dict) else 0.0
        return feats

