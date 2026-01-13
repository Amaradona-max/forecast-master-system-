from __future__ import annotations

from typing import Any

from ml_engine.performance_targets import CHAMPIONSHIP_TARGETS


class ChampionshipSpecialist:
    def adapt_features(self, *, championship: str, features: dict[str, Any]) -> dict[str, Any]:
        target = CHAMPIONSHIP_TARGETS.get(championship, {})
        out = dict(features)
        out["championship"] = championship
        out["championship_key_features"] = list(target.get("key_features", []))
        return out

