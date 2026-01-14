from __future__ import annotations

import asyncio
import contextlib
import json
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from api_gateway.app.auto_refresh_orchestrator import AutoRefreshOrchestrator
from api_gateway.app.local_files import load_calendar_fixtures
from api_gateway.app.services import PredictionService
from api_gateway.app.settings import settings
from api_gateway.app.state import AppState, LiveMatchState
from api_gateway.app.ws import LiveUpdateEvent, WebSocketHub
from api_gateway.routes import accuracy, live, overview, predictions, system_admin


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions.router)
app.include_router(live.router)
app.include_router(accuracy.router)
app.include_router(overview.router)
app.include_router(system_admin.router)


@app.on_event("startup")
async def startup() -> None:
    app.state.app_state = AppState()
    app.state.ws_hub = WebSocketHub()
    if settings.real_data_only and settings.data_provider == "mock":
        app.state.data_error = "real_data_provider_required"
        return
    if settings.data_provider == "mock":
        await _seed_from_mock(app.state.app_state, app.state.ws_hub)
    if settings.data_provider == "api_football":
        await _seed_from_api_football(app.state.app_state, app.state.ws_hub)
    if settings.data_provider == "local_files":
        await _seed_from_local_files(app.state.app_state, app.state.ws_hub)

    if settings.simulate_live_updates and settings.data_provider == "mock":
        app.state.sim_task = asyncio.create_task(_simulate_live_updates(app.state.app_state, app.state.ws_hub))


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "sim_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task


@app.websocket("/ws/live-updates")
async def live_updates(ws: WebSocket) -> None:
    hub: WebSocketHub = app.state.ws_hub
    await hub.connect(ws)
    try:
        await hub.broadcast(LiveUpdateEvent(type="connected", payload={"ts": time.time()}))
        async for evt in hub.iter_events(ws):
            if evt.get("type") == "subscribe" and isinstance(evt.get("match_id"), str):
                await ws.send_json({"type": "subscribed", "payload": {"match_id": evt["match_id"], "ts": time.time()}})
    finally:
        await hub.disconnect(ws)


async def _seed_from_mock(state: AppState, hub: WebSocketHub) -> None:
    predictor = PredictionService()
    orchestrator = AutoRefreshOrchestrator()
    now0 = time.time()
    seed_matches = _seed_fixtures(now0)
    for m in seed_matches:
        context0: dict[str, Any] = {"ts_utc": datetime.fromtimestamp(now0, tz=timezone.utc).isoformat()}
        context0.update(orchestrator.smart_update_context(m, now_unix=now0))
        result0 = predictor.predict_match(
            championship=m.championship,
            home_team=m.home_team,
            away_team=m.away_team,
            status=m.status,
            context=context0,
        )
        m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain})
        m.update(next_update_unix=orchestrator.compute_next_update_unix(m, now_unix=now0))
        await state.upsert_match(m)
        await hub.broadcast(
            LiveUpdateEvent(
                type="match_update",
                payload={
                    "match_id": m.match_id,
                    "championship": m.championship,
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                    "status": m.status,
                    "matchday": m.matchday,
                    "kickoff_unix": m.kickoff_unix,
                    "updated_at_unix": m.updated_at_unix,
                    "probabilities": m.probabilities,
                    "meta": m.meta,
                },
            )
        )


async def _simulate_live_updates(state: AppState, hub: WebSocketHub) -> None:
    predictor = PredictionService()
    rng = random.Random(20260112)
    orchestrator = AutoRefreshOrchestrator()

    now0 = time.time()
    seed_matches = _seed_fixtures(now0)

    for m in seed_matches:
        context0: dict[str, Any] = {"ts_utc": datetime.fromtimestamp(now0, tz=timezone.utc).isoformat()}
        context0.update(orchestrator.smart_update_context(m, now_unix=now0))
        result0 = predictor.predict_match(
            championship=m.championship,
            home_team=m.home_team,
            away_team=m.away_team,
            status=m.status,
            context=context0,
        )
        m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain})
        m.update(next_update_unix=orchestrator.compute_next_update_unix(m, now_unix=now0))
        await state.upsert_match(m)
        await hub.broadcast(
            LiveUpdateEvent(
                type="match_update",
                payload={
                    "match_id": m.match_id,
                    "championship": m.championship,
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                    "status": m.status,
                    "matchday": m.matchday,
                    "kickoff_unix": m.kickoff_unix,
                    "updated_at_unix": m.updated_at_unix,
                    "probabilities": m.probabilities,
                    "meta": m.meta,
                },
            )
        )

    while True:
        matches = await state.list_matches()
        now_unix = time.time()
        now = datetime.fromtimestamp(now_unix, tz=timezone.utc)
        due = [m for m in matches if (m.next_update_unix is None) or (m.next_update_unix <= now_unix)]
        for m in due:
            status = _next_status(m.status, rng)
            context: dict[str, Any] = {"ts_utc": now.isoformat()}
            if status == "LIVE":
                context["events"] = _random_events(rng)
            context.update(orchestrator.smart_update_context(m, now_unix=now_unix))
            result = predictor.predict_match(
                championship=m.championship,
                home_team=m.home_team,
                away_team=m.away_team,
                status=status,
                context=context,
            )
            meta = {"context": context, "explain": result.explain}
            if status == "FINISHED":
                prev_pm = m.meta.get("_post_match_updates", 0)
                if not isinstance(prev_pm, int):
                    prev_pm = 0
                meta["_post_match_updates"] = prev_pm + 1

            m.update(status=status, probabilities=result.probabilities, meta=meta)
            m.update(next_update_unix=orchestrator.compute_next_update_unix(m, now_unix=now_unix))
            await state.upsert_match(m)
            await hub.broadcast(
                LiveUpdateEvent(
                    type="match_update",
                    payload={
                        "match_id": m.match_id,
                        "championship": m.championship,
                        "home_team": m.home_team,
                        "away_team": m.away_team,
                        "status": m.status,
                        "matchday": m.matchday,
                        "kickoff_unix": m.kickoff_unix,
                        "updated_at_unix": m.updated_at_unix,
                        "probabilities": m.probabilities,
                        "meta": m.meta,
                    },
                )
            )
        await asyncio.sleep(1)


def _next_status(cur: str, rng: random.Random) -> str:
    if cur == "PREMATCH":
        return "LIVE" if rng.random() < 0.35 else "PREMATCH"
    if cur == "LIVE":
        return "FINISHED" if rng.random() < 0.18 else "LIVE"
    return "FINISHED"


def _random_events(rng: random.Random) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if rng.random() < 0.15:
        events.append({"type": "goal", "minute": rng.randint(1, 90)})
    if rng.random() < 0.08:
        events.append({"type": "var", "minute": rng.randint(1, 90)})
    return events


def _seed_fixtures(now0: float) -> list[LiveMatchState]:
    teams: dict[str, list[str]] = {
        "serie_a": ["Inter", "Milan", "Juventus", "Napoli", "Roma", "Lazio", "Atalanta", "Fiorentina"],
        "premier_league": ["Arsenal", "Chelsea", "Liverpool", "Man City", "Man United", "Tottenham", "Newcastle", "Aston Villa"],
        "la_liga": ["Barcelona", "Real Madrid", "Atletico", "Sevilla", "Villarreal", "Valencia", "Betis", "Sociedad"],
        "bundesliga": ["Bayern", "Dortmund", "Leipzig", "Leverkusen", "Frankfurt", "Stuttgart", "Wolfsburg", "Freiburg"],
        "eliteserien": ["Bodo/Glimt", "Molde", "Brann", "Rosenborg", "Viking", "Lillestrom", "Sarpsborg", "Tromso"],
    }

    fixtures: list[LiveMatchState] = []
    for champ, t in teams.items():
        day_past = 20
        day_next = 21

        for i in range(4):
            home = t[(2 * i) % len(t)]
            away = t[(2 * i + 1) % len(t)]
            m = LiveMatchState(
                match_id=f"{champ}_{day_past}_{i+1:02d}",
                championship=champ,
                home_team=home,
                away_team=away,
                status="FINISHED",
            )
            kickoff = now0 - (36 * 3600) + (i * 2 * 3600)
            m.update(matchday=day_past, kickoff_unix=kickoff)
            fixtures.append(m)

        for i in range(4):
            home = t[(2 * i + 4) % len(t)]
            away = t[(2 * i + 5) % len(t)]
            m = LiveMatchState(
                match_id=f"{champ}_{day_next}_{i+1:02d}",
                championship=champ,
                home_team=home,
                away_team=away,
                status="PREMATCH",
            )
            kickoff = now0 + (10 * 3600) + (i * 2 * 3600)
            m.update(matchday=day_next, kickoff_unix=kickoff)
            fixtures.append(m)

    return fixtures


def _parse_matchday(round_label: str | None) -> int | None:
    if not round_label:
        return None
    s = str(round_label)
    digits: list[str] = []
    cur: list[str] = []
    for ch in s:
        if ch.isdigit():
            cur.append(ch)
        else:
            if cur:
                digits.append("".join(cur))
                cur.clear()
    if cur:
        digits.append("".join(cur))
    if not digits:
        return None
    try:
        return int(digits[-1])
    except Exception:
        return None


def _map_api_football_status(short: str | None) -> str:
    s = str(short or "").upper()
    if s in {"FT", "AET", "PEN"}:
        return "FINISHED"
    if s in {"NS", "TBD"}:
        return "PREMATCH"
    if s in {"1H", "2H", "HT", "ET", "P", "LIVE"}:
        return "LIVE"
    if s in {"PST", "CANC", "ABD", "SUSP", "INT"}:
        return "PREMATCH"
    return "PREMATCH"


def _http_get_json(url: str, *, headers: dict[str, str]) -> Any:
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


async def _seed_from_api_football(state: AppState, hub: WebSocketHub) -> None:
    if not settings.api_football_key:
        app.state.data_error = "api_football_key_missing"
        return
    if not settings.api_football_league_ids:
        app.state.data_error = "api_football_config_missing"
        return
    if settings.real_data_only and not os.path.exists(settings.ratings_path):
        app.state.data_error = "ratings_missing"
        return

    predictor = PredictionService()
    orchestrator = AutoRefreshOrchestrator()

    now_dt = datetime.now(timezone.utc)
    from_day = (now_dt - timedelta(days=3)).date()
    days_ahead = int(getattr(settings, "fixtures_days_ahead", 90) or 90)
    to_day = (now_dt + timedelta(days=max(7, days_ahead))).date()
    headers = {"x-apisports-key": settings.api_football_key}

    total_added = 0
    last_error: str | None = None

    for champ, league_id in settings.api_football_league_ids.items():
        season = settings.api_football_season_years.get(champ)
        if not season:
            last_error = f"api_football_season_missing:{champ}"
            continue

        base_params = {"league": league_id, "season": season, "timezone": "UTC"}
        qs = urlencode({**base_params, "from": from_day.isoformat(), "to": to_day.isoformat()})
        url = f"{settings.api_football_base_url.rstrip('/')}/fixtures?{qs}"
        try:
            payload = _http_get_json(url, headers=headers)
        except Exception:
            last_error = "api_football_fetch_failed"
            if settings.real_data_only:
                app.state.data_error = last_error
            continue

        items = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            if isinstance(payload, dict):
                errors = payload.get("errors")
                msg = payload.get("message") or payload.get("error")
                if errors or msg:
                    last_error = f"api_football_error:{str(msg or errors)}"
                else:
                    last_error = "api_football_bad_response"
            continue
        if not items:
            next_n = int(getattr(settings, "api_football_fixtures_next", 50) or 50)
            next_n = max(10, min(200, next_n))
            qs2 = urlencode({**base_params, "next": next_n})
            url2 = f"{settings.api_football_base_url.rstrip('/')}/fixtures?{qs2}"
            try:
                payload2 = _http_get_json(url2, headers=headers)
            except Exception:
                payload2 = None
            items2 = payload2.get("response") if isinstance(payload2, dict) else None
            if isinstance(items2, list) and items2:
                items = items2

        now0 = time.time()
        for it in items:
            if not isinstance(it, dict):
                continue
            fixture = it.get("fixture") if isinstance(it.get("fixture"), dict) else {}
            league = it.get("league") if isinstance(it.get("league"), dict) else {}
            teams = it.get("teams") if isinstance(it.get("teams"), dict) else {}
            home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
            away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
            status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
            goals = it.get("goals") if isinstance(it.get("goals"), dict) else {}

            fixture_id = fixture.get("id")
            if fixture_id is None:
                continue
            match_id = f"{champ}_{fixture_id}"

            kickoff_iso = fixture.get("date")
            kickoff_unix = None
            if isinstance(kickoff_iso, str) and kickoff_iso:
                try:
                    kickoff_unix = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).timestamp()
                except Exception:
                    kickoff_unix = None

            if kickoff_unix is not None:
                if kickoff_unix < (now0 - 60 * 60 * 24 * 7):
                    continue

            md = _parse_matchday(league.get("round"))
            st = _map_api_football_status(status.get("short"))

            m = LiveMatchState(
                match_id=match_id,
                championship=champ,
                home_team=str(home.get("name") or "").strip() or "Home",
                away_team=str(away.get("name") or "").strip() or "Away",
                status=st,
            )
            m.update(matchday=md, kickoff_unix=kickoff_unix)

            context0: dict[str, Any] = {"ts_utc": datetime.fromtimestamp(now0, tz=timezone.utc).isoformat()}
            context0.update(orchestrator.smart_update_context(m, now_unix=now0))
            context0["source"] = {"provider": "api_football", "fixture_id": fixture_id, "league_id": league_id, "season": season}
            if st == "FINISHED":
                hg = goals.get("home")
                ag = goals.get("away")
                if isinstance(hg, (int, float)) and isinstance(ag, (int, float)):
                    context0["final_score"] = {"home": int(hg), "away": int(ag)}

            try:
                result0 = predictor.predict_match(
                    championship=m.championship,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    status=m.status,
                    context=context0,
                )
                m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain})
            except Exception as e:
                m.update(
                    probabilities={"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3},
                    meta={"context": context0, "explain": {"error": "prediction_failed", "error_type": type(e).__name__}},
                )

            await state.upsert_match(m)
            total_added += 1
            await hub.broadcast(
                LiveUpdateEvent(
                    type="match_update",
                    payload={
                        "match_id": m.match_id,
                        "championship": m.championship,
                        "home_team": m.home_team,
                        "away_team": m.away_team,
                        "status": m.status,
                        "matchday": m.matchday,
                        "kickoff_unix": m.kickoff_unix,
                        "updated_at_unix": m.updated_at_unix,
                        "probabilities": m.probabilities,
                        "meta": m.meta,
                    },
                )
            )

    if total_added == 0:
        app.state.data_error = last_error or "api_football_no_matches"


async def _seed_from_local_files(state: AppState, hub: WebSocketHub) -> None:
    if settings.real_data_only and not os.path.exists(settings.ratings_path):
        app.state.data_error = "ratings_missing"
        return
    if settings.real_data_only:
        try:
            rp = Path(settings.ratings_path)
            src = json.loads(rp.read_text(encoding="utf-8")).get("meta", {}).get("source")
        except Exception:
            src = None
        if src != "local_files":
            app.state.data_error = "ratings_not_from_local_files"
            return

    base_dir = Path(settings.local_data_dir).resolve()
    cal_path = (base_dir / settings.local_calendar_filename).resolve()
    if settings.real_data_only and not cal_path.exists():
        app.state.data_error = "calendar_missing"
        return

    predictor = PredictionService()
    orchestrator = AutoRefreshOrchestrator()
    now0 = time.time()
    now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)

    for champ in settings.api_football_league_ids.keys():
        fixtures = load_calendar_fixtures(base_dir=base_dir, calendar_filename=settings.local_calendar_filename, championship=champ, now_utc=now_dt)
        for i, f in enumerate(fixtures):
            match_id = f"{champ}_local_{f.matchday or 0}_{i:04d}"
            m = LiveMatchState(
                match_id=match_id,
                championship=champ,
                home_team=f.home_team,
                away_team=f.away_team,
                status=f.status,
            )
            m.update(matchday=f.matchday, kickoff_unix=f.kickoff_unix)

            context0: dict[str, Any] = {"ts_utc": now_dt.isoformat()}
            context0.update(orchestrator.smart_update_context(m, now_unix=now0))
            if isinstance(f.source, dict):
                context0["source"] = dict(f.source)
            if f.final_score is not None:
                context0["final_score"] = dict(f.final_score)

            try:
                result0 = predictor.predict_match(
                    championship=m.championship,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    status="PREMATCH" if m.status == "FINISHED" else m.status,
                    context=context0,
                )
                m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain})
            except Exception as e:
                m.update(
                    probabilities={"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3},
                    meta={"context": context0, "explain": {"error": "prediction_failed", "error_type": type(e).__name__}},
                )

            await state.upsert_match(m)
            await hub.broadcast(
                LiveUpdateEvent(
                    type="match_update",
                    payload={
                        "match_id": m.match_id,
                        "championship": m.championship,
                        "home_team": m.home_team,
                        "away_team": m.away_team,
                        "status": m.status,
                        "matchday": m.matchday,
                        "kickoff_unix": m.kickoff_unix,
                        "updated_at_unix": m.updated_at_unix,
                        "probabilities": m.probabilities,
                        "meta": m.meta,
                    },
                )
            )
