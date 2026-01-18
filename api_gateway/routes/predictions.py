from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from api_gateway.app.schemas import BatchPredictionRequest, BatchPredictionResponse, MatchPrediction
from api_gateway.app.settings import settings
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
        if settings.real_data_only:
            existing = await state.get_match(match.match_id)
            if existing is None:
                raise HTTPException(status_code=404, detail="real_data_match_not_found")
            meta = existing.meta if isinstance(existing.meta, dict) else {}
            ctx = meta.get("context") if isinstance(meta.get("context"), dict) else {}
            src = ctx.get("source") if isinstance(ctx.get("source"), dict) else {}
            if str(src.get("provider") or "").strip() != "football_data":
                raise HTTPException(status_code=404, detail="real_data_match_not_from_football_data")
            alpha = await state.get_calibration_alpha(existing.championship)
            context0 = dict(ctx)
            context0["calibration"] = {"alpha": float(alpha)}
            live = existing
        else:
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
            championship=live.championship,
            match_id=live.match_id,
            home_team=live.home_team,
            away_team=live.away_team,
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
        try:
            p1 = float(probs.get("home_win", 0.0) or 0.0)
            px = float(probs.get("draw", 0.0) or 0.0)
            p2 = float(probs.get("away_win", 0.0) or 0.0)
            pick = "home_win" if (p1 >= px and p1 >= p2) else "draw" if (px >= p1 and px >= p2) else "away_win"
            p_pick = float(probs.get(pick, 0.0) or 0.0)
            conf = float(result.confidence) if isinstance(result.confidence, (int, float)) else 0.0
            if conf < 0.0:
                conf = 0.0
            if conf > 1.0:
                conf = 1.0
            await state.upsert_prediction_history(
                match_id=str(live.match_id),
                championship=str(live.championship),
                home_team=str(live.home_team),
                away_team=str(live.away_team),
                market="1X2",
                predicted_pick=str(pick),
                predicted_prob=float(p_pick),
                confidence=float(conf),
                kickoff_unix=float(live.kickoff_unix) if isinstance(live.kickoff_unix, (int, float)) else None,
            )
        except Exception:
            pass

        predictions.append(
            MatchPrediction(
                match_id=live.match_id,
                championship=live.championship,
                home_team=live.home_team,
                away_team=live.away_team,
                status=live.status,
                updated_at_unix=live.updated_at_unix,
                probabilities=probs,
                explain=result.explain,
            )
        )

    response.headers["x-cache-hits"] = str(int(cache_hits))
    response.headers["x-cache-misses"] = str(int(cache_misses))
    return BatchPredictionResponse(generated_at_utc=datetime.now(timezone.utc), predictions=predictions)
