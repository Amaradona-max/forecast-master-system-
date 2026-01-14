from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api_gateway.app.schemas import (
    ChampionshipsOverviewResponse,
    ChampionshipOverview,
    MatchdayBlock,
    OverviewMatch,
)
from api_gateway.app.settings import settings
from api_gateway.app.state import AppState
from api_gateway.app.ws import WebSocketHub
from ml_engine.performance_targets import CHAMPIONSHIP_TARGETS


router = APIRouter()

class SystemStatusResponse(BaseModel):
    data_provider: str
    real_data_only: bool
    data_error: str | None = None
    matches_loaded: int
    api_football_key_present: bool
    api_football_leagues_configured: int
    api_football_seasons_configured: int
    now_utc: datetime


@router.get("/api/v1/system/status", response_model=SystemStatusResponse)
async def system_status(request: Request) -> SystemStatusResponse:
    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    if not hasattr(request.app.state, "ws_hub"):
        request.app.state.ws_hub = WebSocketHub()
    state = request.app.state.app_state
    matches = await state.list_matches()
    return SystemStatusResponse(
        data_provider=settings.data_provider,
        real_data_only=settings.real_data_only,
        data_error=getattr(request.app.state, "data_error", None),
        matches_loaded=len(matches),
        api_football_key_present=bool(settings.api_football_key),
        api_football_leagues_configured=len(settings.api_football_league_ids or {}),
        api_football_seasons_configured=len(settings.api_football_season_years or {}),
        now_utc=datetime.now(timezone.utc),
    )


@router.get("/api/v1/overview/championships", response_model=ChampionshipsOverviewResponse)
async def championships_overview(request: Request) -> ChampionshipsOverviewResponse:
    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    if not hasattr(request.app.state, "ws_hub"):
        request.app.state.ws_hub = WebSocketHub()
    state = request.app.state.app_state
    matches = await state.list_matches()
    if not matches and getattr(request.app.state, "data_error", None) is None:
        now_unix0 = datetime.now(timezone.utc).timestamp()
        last_attempt = getattr(request.app.state, "_seed_attempted_unix", 0.0)
        if not isinstance(last_attempt, (int, float)):
            last_attempt = 0.0
        if (now_unix0 - float(last_attempt)) >= 60.0:
            request.app.state._seed_attempted_unix = now_unix0
            try:
                if settings.data_provider == "api_football":
                    from api_gateway.main import _seed_from_api_football  # type: ignore

                    await _seed_from_api_football(request.app.state.app_state, request.app.state.ws_hub)
                elif settings.data_provider == "local_files":
                    from api_gateway.main import _seed_from_local_files  # type: ignore

                    await _seed_from_local_files(request.app.state.app_state, request.app.state.ws_hub)
                elif settings.data_provider == "mock":
                    from api_gateway.main import _seed_from_mock  # type: ignore

                    await _seed_from_mock(request.app.state.app_state, request.app.state.ws_hub)
            except Exception:
                pass
            matches = await state.list_matches()
    now_unix = datetime.now(timezone.utc).timestamp()
    predictions_start_unix = datetime(2026, 1, 14, tzinfo=timezone.utc).timestamp() if settings.real_data_only else 0.0
    if settings.data_provider == "api_football" and not matches:
        detail = getattr(request.app.state, "data_error", None) or "api_football_no_matches"
        raise HTTPException(status_code=503, detail=str(detail))
    if settings.real_data_only and getattr(request.app.state, "data_error", None):
        raise HTTPException(status_code=503, detail=str(request.app.state.data_error))
    if settings.real_data_only and not matches:
        raise HTTPException(status_code=503, detail="real_data_not_loaded")

    by_champ: dict[str, list] = {}
    for m in matches:
        by_champ.setdefault(m.championship, []).append(m)

    payload: list[ChampionshipOverview] = []
    for champ in ["serie_a", "premier_league", "la_liga", "bundesliga", "eliteserien"]:
        rows = by_champ.get(champ, [])
        mapped: list[OverviewMatch] = []
        for m in rows:
            probs0 = dict(m.probabilities or {})
            probs: dict[str, float] = {}
            for k in ("home_win", "draw", "away_win"):
                try:
                    v = float(probs0.get(k, 0.0) or 0.0)
                except Exception:
                    v = 0.0
                probs[k] = max(v, 0.0)
            s = probs["home_win"] + probs["draw"] + probs["away_win"]
            if s <= 0:
                probs = {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
            else:
                probs = {k: v / s for k, v in probs.items()}
            conf = max(probs.values())
            explain = {}
            source = {}
            final_score = None
            if isinstance(m.meta, dict):
                x = m.meta.get("explain")
                if isinstance(x, dict):
                    explain = x
                ctx = m.meta.get("context")
                if isinstance(ctx, dict):
                    s = ctx.get("source")
                    if isinstance(s, dict):
                        source = s
                    fs = ctx.get("final_score")
                    if isinstance(fs, dict):
                        hg = fs.get("home")
                        ag = fs.get("away")
                        if isinstance(hg, int) and isinstance(ag, int):
                            final_score = {"home": int(hg), "away": int(ag)}

            kickoff_unix = m.kickoff_unix
            kickoff_dt = None
            if kickoff_unix is not None:
                try:
                    kickoff_dt = datetime.fromtimestamp(float(kickoff_unix), tz=timezone.utc)
                except Exception:
                    kickoff_dt = None

            in_scope = True
            if settings.real_data_only:
                in_scope = (kickoff_dt is not None) and (kickoff_dt.year in {2025, 2026})
            if not in_scope:
                continue

            mapped.append(
                OverviewMatch(
                    match_id=m.match_id,
                    championship=champ,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    status=m.status,
                    matchday=m.matchday,
                    kickoff_unix=kickoff_unix,
                    updated_at_unix=m.updated_at_unix,
                    probabilities=probs,
                    confidence=conf,
                    explain=explain,
                    source=source,
                    final_score=final_score,
                )
            )

        target = CHAMPIONSHIP_TARGETS.get(champ, {})
        title = {
            "serie_a": "Serie A",
            "premier_league": "Premier League",
            "la_liga": "La Liga",
            "bundesliga": "Bundesliga",
            "eliteserien": "Eliteserien",
        }.get(champ, champ)

        by_md: dict[int | None, list[OverviewMatch]] = {}
        for m in mapped:
            by_md.setdefault(m.matchday, []).append(m)

        matchdays: list[MatchdayBlock] = []
        for md, ms in sorted(by_md.items(), key=lambda it: (it[0] is None, it[0] or 0)):
            label = f"Giornata {md}" if md is not None else "Giornata"
            ms.sort(key=lambda x: (x.kickoff_unix or 0.0, x.match_id))
            matchdays.append(MatchdayBlock(matchday_number=md, matchday_label=label, matches=ms))

        matchdays_future: list[MatchdayBlock] = []
        for md in matchdays:
            ms_future = [
                m
                for m in md.matches
                if (m.status != "FINISHED") and (m.kickoff_unix is not None) and (m.kickoff_unix >= max(now_unix, predictions_start_unix))
            ]
            if ms_future:
                matchdays_future.append(MatchdayBlock(matchday_number=md.matchday_number, matchday_label=md.matchday_label, matches=ms_future))
        active_md = matchdays_future[0] if matchdays_future else (matchdays[0] if matchdays else None)

        active_matches = list(active_md.matches) if active_md is not None else []
        active_to_play = [m for m in active_matches if m.status != "FINISHED"]
        top = sorted(active_to_play, key=lambda x: x.confidence, reverse=True)[:5]
        to_play = [m for m in top if m.confidence >= 0.7]
        finished = [m for m in mapped if m.status == "FINISHED"]

        payload.append(
            ChampionshipOverview(
                championship=champ,
                title=title,
                accuracy_target=target.get("accuracy_target"),
                key_features=list(target.get("key_features", [])),
                matchdays=matchdays_future,
                top_matches=top,
                to_play_ge_70=to_play,
                finished=finished,
            )
        )

    return ChampionshipsOverviewResponse(generated_at_utc=datetime.now(timezone.utc), championships=payload)
