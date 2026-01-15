from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api_gateway.app.schemas import BatchPredictionRequest, BatchPredictionResponse, MatchPrediction
from api_gateway.app.services import PredictionService
from api_gateway.app.state import LiveMatchState


router = APIRouter()

def _calibrate_probs(probs: dict[str, float], alpha: float) -> dict[str, float]:
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


@router.post("/api/v1/predictions/batch", response_model=BatchPredictionResponse)
async def batch_predictions(req: BatchPredictionRequest, request: Request) -> BatchPredictionResponse:
    prediction_service = PredictionService()
    state = request.app.state.app_state

    predictions: list[MatchPrediction] = []
    for match in req.matches:
        alpha = await state.get_calibration_alpha(match.championship)
        context0 = dict(match.context or {})
        context0["calibration"] = {"alpha": float(alpha)}
        live = LiveMatchState(
            match_id=match.match_id,
            championship=match.championship,
            home_team=match.home_team,
            away_team=match.away_team,
            status="PREMATCH",
        )
        if match.kickoff_utc is not None:
            live.update(kickoff_unix=match.kickoff_utc.timestamp())
        result = prediction_service.predict_match(
            championship=match.championship,
            home_team=match.home_team,
            away_team=match.away_team,
            status=live.status,
            context=context0,
        )
        probs = _calibrate_probs(dict(result.probabilities or {}), alpha)
        live.update(probabilities=probs, meta={"context": context0, "explain": result.explain})
        await state.upsert_match(live)

        predictions.append(
            MatchPrediction(
                match_id=live.match_id,
                championship=match.championship,
                home_team=match.home_team,
                away_team=match.away_team,
                status=live.status,
                updated_at_unix=live.updated_at_unix,
                probabilities=probs,
                explain=result.explain,
            )
        )

    return BatchPredictionResponse(generated_at_utc=datetime.now(timezone.utc), predictions=predictions)
