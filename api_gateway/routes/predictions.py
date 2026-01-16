from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from api_gateway.app.schemas import BatchPredictionRequest, BatchPredictionResponse, MatchPrediction
from api_gateway.app.services import PredictionService
from api_gateway.app.state import LiveMatchState
from ml_engine.resilience.bulkheads import run_cpu


router = APIRouter()

@router.post("/api/v1/predictions/batch", response_model=BatchPredictionResponse)
async def batch_predictions(req: BatchPredictionRequest, request: Request, response: Response) -> BatchPredictionResponse:
    prediction_service = PredictionService()
    state = request.app.state.app_state

    predictions: list[MatchPrediction] = []
    cache_hits = 0
    cache_misses = 0
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
        result = await run_cpu(
            prediction_service.predict_match,
            championship=match.championship,
            match_id=match.match_id,
            home_team=match.home_team,
            away_team=match.away_team,
            status=live.status,
            kickoff_unix=live.kickoff_unix,
            context=context0,
        )
        if isinstance(result.explain, dict):
            c = result.explain.get("cache")
            if isinstance(c, dict):
                if bool(c.get("hit")):
                    cache_hits += 1
                else:
                    cache_misses += 1
        probs = dict(result.probabilities or {})
        live.update(probabilities=probs, meta={"context": context0, "explain": result.explain, "confidence": result.confidence, "ranges": result.ranges})
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

    response.headers["x-cache-hits"] = str(int(cache_hits))
    response.headers["x-cache-misses"] = str(int(cache_misses))
    return BatchPredictionResponse(generated_at_utc=datetime.now(timezone.utc), predictions=predictions)
