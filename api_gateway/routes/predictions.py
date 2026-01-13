from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from api_gateway.app.schemas import BatchPredictionRequest, BatchPredictionResponse, MatchPrediction
from api_gateway.app.services import PredictionService
from api_gateway.app.state import LiveMatchState


router = APIRouter()


@router.post("/api/v1/predictions/batch", response_model=BatchPredictionResponse)
async def batch_predictions(req: BatchPredictionRequest, request: Request) -> BatchPredictionResponse:
    prediction_service = PredictionService()
    state = request.app.state.app_state

    predictions: list[MatchPrediction] = []
    for match in req.matches:
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
            context=match.context,
        )
        live.update(probabilities=result.probabilities, meta={"explain": result.explain})
        await state.upsert_match(live)

        predictions.append(
            MatchPrediction(
                match_id=live.match_id,
                championship=match.championship,
                home_team=match.home_team,
                away_team=match.away_team,
                status=live.status,
                updated_at_unix=live.updated_at_unix,
                probabilities=result.probabilities,
                explain=result.explain,
            )
        )

    return BatchPredictionResponse(generated_at_utc=datetime.now(timezone.utc), predictions=predictions)
