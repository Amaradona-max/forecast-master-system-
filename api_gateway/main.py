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
from urllib.error import HTTPError, URLError
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
from api_gateway.middleware.rate_limit import rate_limit_middleware
from api_gateway.middleware.request_limits import request_limits_middleware
from api_gateway.routes import accuracy, live, overview, predictions, system_admin
from ml_engine.cache.sqlite_cache import SqliteCache, recover_corrupt_sqlite_db
from ml_engine.config import cache_db_path
from ml_engine.resilience.bulkheads import run_cpu
from ml_engine.resilience.timeouts import default_deadline_ms, reset_deadline, set_deadline_ms


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def _request_limits_middleware(request, call_next):
    return await request_limits_middleware(request, call_next)

@app.middleware("http")
async def _rate_limit_middleware(request, call_next):
    return await rate_limit_middleware(request, call_next)

@app.middleware("http")
async def metrics_middleware(request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    route = str(getattr(request.url, "path", "") or "")
    is_err = bool(int(getattr(resp, "status_code", 500) or 500) >= 400)
    hits = resp.headers.get("x-cache-hits")
    misses = resp.headers.get("x-cache-misses")
    try:
        h = int(hits) if hits is not None else 0
    except Exception:
        h = 0
    try:
        m = int(misses) if misses is not None else 0
    except Exception:
        m = 0
    try:
        SqliteCache(db_path=cache_db_path()).incr_runtime_metrics(day=day, route=route, latency_ms=float(dt_ms), is_error=is_err, cache_hits=h, cache_misses=m)
    except Exception:
        pass
    return resp

app.include_router(predictions.router)
app.include_router(live.router)
app.include_router(accuracy.router)
app.include_router(overview.router)
app.include_router(system_admin.router)


async def _run_cpu_with_deadline(fn, /, *args: Any, **kwargs: Any):
    tok = set_deadline_ms(default_deadline_ms())
    try:
        return await run_cpu(fn, *args, **kwargs)
    finally:
        reset_deadline(tok)


def _effective_data_provider() -> str:
    provider = str(getattr(settings, "data_provider", "") or "").strip()
    if not settings.real_data_only and provider == "api_football" and bool(getattr(settings, "football_data_key", None)):
        return "football_data"
    return provider


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


@app.on_event("startup")
async def startup() -> None:
    app.state.app_state = AppState()
    app.state.ws_hub = WebSocketHub()
    try:
        ok = bool(SqliteCache(db_path=cache_db_path()).quick_check())
    except Exception:
        ok = False
    if not ok:
        with contextlib.suppress(Exception):
            recover_corrupt_sqlite_db(db_path=cache_db_path())
    provider = _effective_data_provider()
    if settings.real_data_only and provider != "football_data":
        app.state.data_error = "real_data_only_requires_football_data_provider"
        return
    if settings.real_data_only:
        await app.state.app_state.clear_all()
    if provider == "mock":
        await _seed_from_mock(app.state.app_state, app.state.ws_hub)
    if provider == "api_football":
        await _seed_from_api_football(app.state.app_state, app.state.ws_hub)
    if provider == "football_data":
        await _seed_from_football_data(app.state.app_state, app.state.ws_hub)
    if provider == "local_files":
        await _seed_from_local_files(app.state.app_state, app.state.ws_hub)

    if settings.simulate_live_updates and provider == "mock":
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
        if m.matchday is not None:
            context0["matchday"] = int(m.matchday)
        result0 = await _run_cpu_with_deadline(
            predictor.predict_match,
            championship=m.championship,
            match_id=m.match_id,
            home_team=m.home_team,
            away_team=m.away_team,
            status=m.status,
            kickoff_unix=m.kickoff_unix,
            context=context0,
        )
        m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain, "confidence": result0.confidence, "ranges": result0.ranges})
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
        if m.matchday is not None:
            context0["matchday"] = int(m.matchday)
        result0 = await _run_cpu_with_deadline(
            predictor.predict_match,
            championship=m.championship,
            match_id=m.match_id,
            home_team=m.home_team,
            away_team=m.away_team,
            status=m.status,
            kickoff_unix=m.kickoff_unix,
            context=context0,
        )
        m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain, "confidence": result0.confidence, "ranges": result0.ranges})
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
            result = await _run_cpu_with_deadline(
                predictor.predict_match,
                championship=m.championship,
                match_id=m.match_id,
                home_team=m.home_team,
                away_team=m.away_team,
                status=status,
                kickoff_unix=m.kickoff_unix,
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


def _map_football_data_status(status: str | None) -> str:
    s = str(status or "").upper()
    if s in {"FINISHED"}:
        return "FINISHED"
    if s in {"IN_PLAY", "PAUSED"}:
        return "LIVE"
    if s in {"SCHEDULED", "TIMED", "POSTPONED", "SUSPENDED", "CANCELED"}:
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
        alpha = await state.get_calibration_alpha(champ)

        base_params = {"league": league_id, "season": season, "timezone": "UTC"}
        qs = urlencode({**base_params, "from": from_day.isoformat(), "to": to_day.isoformat()})
        url = f"{settings.api_football_base_url.rstrip('/')}/fixtures?{qs}"
        try:
            payload = _http_get_json(url, headers=headers)
        except Exception as e:
            last_error = f"api_football_fetch_failed:{type(e).__name__}"
            if settings.real_data_only:
                app.state.data_error = last_error
            continue

        if isinstance(payload, dict):
            errors = payload.get("errors")
            msg = payload.get("message") or payload.get("error")
            if msg:
                last_error = f"api_football_error:{str(msg)}"
            elif isinstance(errors, dict) and any(bool(v) for v in errors.values()):
                last_error = f"api_football_error:{json.dumps(errors, ensure_ascii=False)}"
            elif isinstance(errors, list) and errors:
                last_error = f"api_football_error:{json.dumps(errors, ensure_ascii=False)}"

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
            if isinstance(payload2, dict):
                errors2 = payload2.get("errors")
                msg2 = payload2.get("message") or payload2.get("error")
                if msg2:
                    last_error = f"api_football_error:{str(msg2)}"
                elif isinstance(errors2, dict) and any(bool(v) for v in errors2.values()):
                    last_error = f"api_football_error:{json.dumps(errors2, ensure_ascii=False)}"
                elif isinstance(errors2, list) and errors2:
                    last_error = f"api_football_error:{json.dumps(errors2, ensure_ascii=False)}"
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
            if m.matchday is not None:
                context0["matchday"] = int(m.matchday)
            if st == "FINISHED":
                hg = goals.get("home")
                ag = goals.get("away")
                if isinstance(hg, (int, float)) and isinstance(ag, (int, float)):
                    context0["final_score"] = {"home": int(hg), "away": int(ag)}
            context0["calibration"] = {"alpha": float(alpha)}

            try:
                result0 = await _run_cpu_with_deadline(
                    predictor.predict_match,
                    championship=m.championship,
                    match_id=m.match_id,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    status=m.status,
                    kickoff_unix=m.kickoff_unix,
                    context=context0,
                )
                m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain, "confidence": result0.confidence, "ranges": result0.ranges})
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


async def _seed_from_football_data(state: AppState, hub: WebSocketHub) -> None:
    raw_key = str(settings.football_data_key or "").strip()
    key = raw_key.strip('"').strip("'").strip()
    if not key:
        app.state.data_error = "football_data_key_missing"
        return
    if not settings.football_data_competition_codes:
        app.state.data_error = "football_data_config_missing"
        return
    if settings.real_data_only and not os.path.exists(settings.ratings_path):
        app.state.data_error = "ratings_missing"
        return

    predictor = PredictionService()
    orchestrator = AutoRefreshOrchestrator()

    now_dt = datetime.now(timezone.utc)
    now0 = time.time()
    until = getattr(app.state, "_football_data_rate_limited_until", 0.0)
    if isinstance(until, (int, float)) and float(until) > now0:
        app.state.data_error = "football_data_http_429:rate_limited"
        return
    from_day = (now_dt - timedelta(days=3)).date()
    days_ahead = int(getattr(settings, "fixtures_days_ahead", 90) or 90)
    to_day = (now_dt + timedelta(days=max(7, days_ahead))).date()
    headers = {"X-Auth-Token": key, "Accept": "application/json", "User-Agent": str(getattr(settings, "app_name", "Forecast Master System API"))}

    total_added = 0
    last_error: str | None = None

    comps = list((settings.football_data_competition_codes or {}).items())
    max_n = int(getattr(settings, "football_data_max_competitions_per_seed", 1) or 1)
    if max_n < 1:
        max_n = 1
    if max_n > len(comps):
        max_n = len(comps)
    if os.getenv("VERCEL") and comps:
        bucket = 600.0
        idx = int(now0 // bucket) % len(comps)
    else:
        idx0 = getattr(app.state, "_football_data_next_competition_index", 0)
        idx = int(idx0) if isinstance(idx0, int) else 0
        if idx < 0:
            idx = 0
    selected: list[tuple[str, str]] = []
    if comps:
        for i in range(max_n):
            selected.append(comps[(idx + i) % len(comps)])
        if not os.getenv("VERCEL"):
            app.state._football_data_next_competition_index = (idx + max_n) % len(comps)

    for champ, code in selected:
        alpha = await state.get_calibration_alpha(champ)
        qs = urlencode({"dateFrom": from_day.isoformat(), "dateTo": to_day.isoformat()})
        url = f"{settings.football_data_base_url.rstrip('/')}/competitions/{code}/matches?{qs}"
        cache_key = f"fd_matches:{code}:{from_day.isoformat()}:{to_day.isoformat()}"
        ttl_seconds = 900.0 if os.getenv("VERCEL") else 240.0
        cached = await state.get_cache_json(cache_key)
        try:
            if cached is not None:
                payload = cached
            else:
                payload = _http_get_json(url, headers=headers)
                await state.set_cache_json(cache_key, payload, ttl_seconds)
        except HTTPError as e:
            body = ""
            try:
                body = (e.read() or b"").decode("utf-8", errors="replace")
            except Exception:
                body = ""
            snippet = body.strip().replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:220] + "…"
            code0 = getattr(e, "code", None)
            if isinstance(code0, int):
                if code0 == 401:
                    last_error = f"football_data_http_401:unauthorized:{snippet}" if snippet else "football_data_http_401:unauthorized"
                    app.state.data_error = last_error
                    return
                elif code0 == 403:
                    last_error = f"football_data_http_403:forbidden:{snippet}" if snippet else "football_data_http_403:forbidden"
                    app.state.data_error = last_error
                    return
                elif code0 == 404:
                    last_error = f"football_data_http_404:not_found:{code}"
                elif code0 == 429:
                    last_error = "football_data_http_429:rate_limited"
                    retry_after = None
                    try:
                        ra = e.headers.get("Retry-After") if getattr(e, "headers", None) is not None else None
                        retry_after = int(str(ra).strip()) if ra is not None else None
                    except Exception:
                        retry_after = None
                    cool = max(120, int(retry_after or 0))
                    if cool > 3600:
                        cool = 3600
                    app.state._football_data_rate_limited_until = time.time() + float(cool)
                    if cached is not None:
                        payload = cached
                    else:
                        app.state.data_error = last_error
                        return
                else:
                    last_error = f"football_data_http_{code0}:{snippet}" if snippet else f"football_data_http_{code0}"
            else:
                last_error = "football_data_fetch_failed:HTTPError"
            if settings.real_data_only:
                app.state.data_error = last_error
            continue
        except URLError as e:
            last_error = f"football_data_network_error:{type(e).__name__}"
            if settings.real_data_only:
                app.state.data_error = last_error
            continue
        except Exception as e:
            last_error = f"football_data_fetch_failed:{type(e).__name__}"
            if settings.real_data_only:
                app.state.data_error = last_error
            continue

        if isinstance(payload, dict):
            msg = payload.get("message") or payload.get("error")
            if msg:
                last_error = f"football_data_error:{str(msg)}"

        items = payload.get("matches") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            if isinstance(payload, dict):
                msg = payload.get("message") or payload.get("error")
                if msg:
                    last_error = f"football_data_error:{str(msg)}"
                else:
                    last_error = "football_data_bad_response"
            continue

        now0 = time.time()
        for it in items:
            if not isinstance(it, dict):
                continue
            match_pk = it.get("id")
            if match_pk is None:
                continue
            match_id = f"{champ}_fd_{match_pk}"

            kickoff_iso = it.get("utcDate")
            kickoff_unix = None
            if isinstance(kickoff_iso, str) and kickoff_iso:
                try:
                    kickoff_unix = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).timestamp()
                except Exception:
                    kickoff_unix = None

            if kickoff_unix is not None and kickoff_unix < (now0 - 60 * 60 * 24 * 7):
                continue

            md0 = it.get("matchday")
            md = int(md0) if isinstance(md0, int) else None
            st = _map_football_data_status(it.get("status"))
            home = it.get("homeTeam") if isinstance(it.get("homeTeam"), dict) else {}
            away = it.get("awayTeam") if isinstance(it.get("awayTeam"), dict) else {}

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
            context0["source"] = {"provider": "football_data", "competition": code, "match_id": match_pk}
            if m.matchday is not None:
                context0["matchday"] = int(m.matchday)
            context0["calibration"] = {"alpha": float(alpha)}

            if st == "FINISHED":
                score = it.get("score") if isinstance(it.get("score"), dict) else {}
                full = score.get("fullTime") if isinstance(score.get("fullTime"), dict) else {}
                hg = full.get("home")
                ag = full.get("away")
                if isinstance(hg, int) and isinstance(ag, int):
                    context0["final_score"] = {"home": int(hg), "away": int(ag)}

            try:
                result0 = await _run_cpu_with_deadline(
                    predictor.predict_match,
                    championship=m.championship,
                    match_id=m.match_id,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    status="PREMATCH" if m.status == "FINISHED" else m.status,
                    kickoff_unix=m.kickoff_unix,
                    context=context0,
                )
                m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain, "confidence": result0.confidence, "ranges": result0.ranges})
            except Exception as e:
                last_error = f"football_data_prediction_failed:{type(e).__name__}"
                if settings.real_data_only:
                    app.state.data_error = last_error
                    continue
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
        app.state.data_error = last_error or "football_data_no_matches"


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
        alpha = await state.get_calibration_alpha(champ)
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
            if m.matchday is not None:
                context0["matchday"] = int(m.matchday)
            if f.final_score is not None:
                context0["final_score"] = dict(f.final_score)
            context0["calibration"] = {"alpha": float(alpha)}

            try:
                result0 = await _run_cpu_with_deadline(
                    predictor.predict_match,
                    championship=m.championship,
                    match_id=m.match_id,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    status="PREMATCH" if m.status == "FINISHED" else m.status,
                    kickoff_unix=m.kickoff_unix,
                    context=context0,
                )
                m.update(probabilities=result0.probabilities, meta={"context": context0, "explain": result0.explain, "confidence": result0.confidence, "ranges": result0.ranges})
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
