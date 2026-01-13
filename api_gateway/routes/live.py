from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api_gateway.app.schemas import LiveProbabilitiesResponse


router = APIRouter()


@router.get("/api/v1/live/{match_id}/probabilities", response_model=LiveProbabilitiesResponse)
async def get_live_probabilities(match_id: str, request: Request) -> LiveProbabilitiesResponse:
    state = request.app.state.app_state
    match = await state.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match_not_found")
    return LiveProbabilitiesResponse(
        match_id=match.match_id,
        status=match.status,
        kickoff_unix=match.kickoff_unix,
        updated_at_unix=match.updated_at_unix,
        probabilities=match.probabilities,
        meta=match.meta,
    )
