from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api_gateway.app.historical_ratings import (
    build_ratings_payload,
    fetch_finished_matches_for_season,
    write_ratings_file,
)
from api_gateway.app.local_files import load_historical_matches
from api_gateway.app.settings import settings
from api_gateway.app.state import AppState


router = APIRouter()


class RebuildRatingsResponse(BaseModel):
    ok: bool
    ratings_path: str
    asof_utc: datetime
    seasons: list[int]
    matches_used: dict[str, int]


@router.post("/api/v1/system/rebuild-ratings", response_model=RebuildRatingsResponse)
async def rebuild_ratings(request: Request) -> RebuildRatingsResponse:
    asof = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    seasons = list(range(int(settings.historical_start_season), int(settings.historical_end_season) + 1))
    championship_matches: dict[str, list] = {}

    if settings.data_provider == "api_football":
        if not settings.api_football_key:
            raise HTTPException(status_code=400, detail="api_football_key_missing")
        for champ, league_id in settings.api_football_league_ids.items():
            all_matches = []
            for season in seasons:
                ms = fetch_finished_matches_for_season(
                    championship=champ,
                    league_id=int(league_id),
                    season_year=int(season),
                    api_base_url=settings.api_football_base_url,
                    api_key=str(settings.api_football_key),
                )
                all_matches.extend(ms)
            all_matches.sort(key=lambda m: m.kickoff_unix)
            championship_matches[champ] = all_matches
    elif settings.data_provider == "local_files":
        base_dir = Path(settings.local_data_dir).resolve()
        for champ in settings.api_football_league_ids.keys():
            ms = load_historical_matches(base_dir=base_dir, championship=champ, start_year=settings.historical_start_season, end_year=settings.historical_end_season)
            championship_matches[champ] = ms
    else:
        raise HTTPException(status_code=400, detail="provider_not_supported")

    payload = build_ratings_payload(championship_matches=championship_matches, asof_unix=asof, source=settings.data_provider)
    write_ratings_file(path=settings.ratings_path, payload=payload)

    request.app.state.data_error = None
    request.app.state.app_state = AppState()

    try:
        if settings.data_provider == "api_football":
            from api_gateway.main import _seed_from_api_football  # type: ignore

            await _seed_from_api_football(request.app.state.app_state, request.app.state.ws_hub)
        elif settings.data_provider == "local_files":
            from api_gateway.main import _seed_from_local_files  # type: ignore

            await _seed_from_local_files(request.app.state.app_state, request.app.state.ws_hub)
    except Exception:
        pass

    used: dict[str, int] = {}
    champs = payload.get("championships") if isinstance(payload, dict) else None
    if isinstance(champs, dict):
        for champ, row in champs.items():
            if isinstance(row, dict) and isinstance(row.get("n_matches_used"), int):
                used[str(champ)] = int(row["n_matches_used"])

    return RebuildRatingsResponse(
        ok=True,
        ratings_path=settings.ratings_path,
        asof_utc=datetime.fromtimestamp(asof, tz=timezone.utc),
        seasons=seasons,
        matches_used=used,
    )
