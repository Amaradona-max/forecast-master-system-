from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ml_engine.ensemble_predictor.service import EnsemblePredictorService
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

    def predict_match(
        self,
        *,
        championship: str,
        home_team: str,
        away_team: str,
        status: str,
        context: dict[str, Any],
    ) -> PredictionResult:
        ctx = dict(context or {})
        ctx["real_data_only"] = settings.real_data_only
        raw = self._ensemble.predict(
            championship=championship,
            home_team=home_team,
            away_team=away_team,
            status=status,
            context=ctx,
        )

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
        return PredictionResult(probabilities=probs, explain=dict(raw.get("explain", {})), confidence=float(conf) if conf is not None else None, ranges=ranges)
