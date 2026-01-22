from __future__ import annotations

import asyncio
import contextlib
import json
import os
import random
import smtplib
import ssl
import time
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from api_gateway.app.auto_refresh_orchestrator import AutoRefreshOrchestrator
from api_gateway.app.backtest_metrics import rebuild_backtest_metrics_to_file
from api_gateway.app.backtest_trends import rebuild_backtest_trends_to_file
from api_gateway.app.calibration_alpha import rebuild_calibration_alpha
from api_gateway.app.decision_gate_tuning import TuneParams, rebuild_decision_gate_tuned
from api_gateway.app.local_files import load_calendar_fixtures
from api_gateway.app.services import PredictionService
from api_gateway.app.settings import settings
from api_gateway.app.state import AppState, LiveMatchState
from api_gateway.app.team_form import rebuild_team_form_from_football_data
from api_gateway.app.ws import LiveUpdateEvent, WebSocketHub
from api_gateway.app.routes.backtest_metrics import router as backtest_metrics_router
from api_gateway.app.routes.backtest_trends import router as backtest_trends_router
from api_gateway.middleware.rate_limit import rate_limit_middleware
from api_gateway.middleware.request_limits import request_limits_middleware
from api_gateway.routes import accuracy, history, insights, live, notifications, overview, predictions, system_admin
from ml_engine.cache.sqlite_cache import SqliteCache, recover_corrupt_sqlite_db
from ml_engine.config import cache_db_path
from ml_engine.resilience.bulkheads import run_cpu
from ml_engine.resilience.timeouts import default_deadline_ms, reset_deadline, set_deadline_ms

try:
    import certifi  # type: ignore

    _CERTIFI_CAFILE = certifi.where()
except Exception:
    _CERTIFI_CAFILE = None


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
app.include_router(history.router)
app.include_router(overview.router)
app.include_router(insights.router)
app.include_router(notifications.router)
app.include_router(system_admin.router)
app.include_router(backtest_metrics_router, prefix="/api")
app.include_router(backtest_trends_router, prefix="/api")


async def _run_cpu_with_deadline(fn, /, *args: Any, **kwargs: Any):
    tok = set_deadline_ms(default_deadline_ms())
    try:
        return await run_cpu(fn, *args, **kwargs)
    finally:
        reset_deadline(tok)


def _effective_data_provider() -> str:
    provider = str(getattr(settings, "data_provider", "") or "").strip()
    if not settings.real_data_only and provider == "api_football":
        if not bool(getattr(settings, "api_football_key", None)) and bool(getattr(settings, "football_data_key", None)):
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


def _parse_utc_iso(s: str) -> datetime | None:
    raw = str(s or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _seed_scheduler(provider: str, state: AppState, hub: WebSocketHub) -> None:
    while True:
        now0 = time.time()
        try:
            refresh_interval = float(getattr(settings, "fixtures_refresh_interval_seconds", 600) or 600)
        except Exception:
            refresh_interval = 600.0
        try:
            season_interval = float(getattr(settings, "fixtures_season_interval_seconds", 86400) or 86400)
        except Exception:
            season_interval = 86400.0

        last_refresh = getattr(app.state, "_refresh_seed_last_unix", 0.0)
        if not isinstance(last_refresh, (int, float)):
            last_refresh = 0.0
        last_season = getattr(app.state, "_season_seed_last_unix", 0.0)
        if not isinstance(last_season, (int, float)):
            last_season = 0.0

        if provider == "football_data":
            if (now0 - float(last_refresh)) >= refresh_interval:
                app.state._refresh_seed_last_unix = now0
                with contextlib.suppress(Exception):
                    await _seed_from_football_data(state, hub)
            if (now0 - float(last_season)) >= season_interval:
                app.state._season_seed_last_unix = now0
                with contextlib.suppress(Exception):
                    await _seed_from_football_data_season(state, hub)
        elif provider == "api_football":
            if (now0 - float(last_refresh)) >= refresh_interval:
                app.state._refresh_seed_last_unix = now0
                with contextlib.suppress(Exception):
                    await _seed_from_api_football(state, hub)

        await asyncio.sleep(30)


async def _rebuild_team_ratings_from_football_data() -> None:
    raw_key = str(settings.football_data_key or "").strip()
    key = raw_key.strip('"').strip("'").strip()
    if not key:
        return
    codes = settings.football_data_competition_codes or {}
    if not isinstance(codes, dict) or not codes:
        return

    from api_gateway.app.historical_ratings import (
        build_ratings_payload,
        fetch_finished_matches_for_range_football_data,
        write_ratings_file,
    )

    now0 = time.time()
    now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)

    start_dt = _parse_utc_iso(str(getattr(settings, "fixtures_season_start_utc", "") or "")) or datetime(2025, 8, 1, tzinfo=timezone.utc)
    end_dt = _parse_utc_iso(str(getattr(settings, "fixtures_season_end_utc", "") or "")) or datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    to_dt = now_dt if now_dt <= end_dt else end_dt
    from_day = start_dt.date().isoformat()
    to_day = to_dt.date().isoformat()

    championship_matches: dict[str, list] = {}
    total_matches = 0
    for champ, code in codes.items():
        try:
            ms = fetch_finished_matches_for_range_football_data(
                championship=str(champ),
                competition_code=str(code),
                date_from_iso=from_day,
                date_to_iso=to_day,
                api_base_url=str(settings.football_data_base_url),
                api_key=key,
            )
        except Exception:
            ms = []
        total_matches += len(ms)
        championship_matches[str(champ)] = ms

    if total_matches <= 0:
        return
    payload = build_ratings_payload(championship_matches=championship_matches, asof_unix=now0, source="football_data")
    write_ratings_file(path=str(settings.ratings_path), payload=payload)


async def _ratings_scheduler(provider: str) -> None:
    while True:
        now0 = time.time()
        if provider != "football_data":
            await asyncio.sleep(300)
            continue
        if not bool(getattr(settings, "ratings_refresh_enabled", True)):
            await asyncio.sleep(300)
            continue

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        weekend_interval = float(getattr(settings, "ratings_weekend_refresh_interval_seconds", 0) or 0)
        if weekend_interval > 0 and now_dt.weekday() >= 5:
            last = getattr(app.state, "_ratings_refresh_last_unix", 0.0)
            if not isinstance(last, (int, float)):
                last = 0.0
            interval = weekend_interval if weekend_interval >= 900 else 900.0
            if (now0 - float(last)) >= interval:
                app.state._ratings_refresh_last_unix = now0
                with contextlib.suppress(Exception):
                    await _rebuild_team_ratings_from_football_data()
        else:
            today = now_dt.date().isoformat()
            last_day = getattr(app.state, "_ratings_refresh_last_day", "")
            if not isinstance(last_day, str):
                last_day = ""
            if today != last_day and now_dt.hour >= 3:
                app.state._ratings_refresh_last_day = today
                app.state._ratings_refresh_last_unix = now0
                with contextlib.suppress(Exception):
                    await _rebuild_team_ratings_from_football_data()

        await asyncio.sleep(300)


async def _form_scheduler(provider: str) -> None:
    import asyncio
    import contextlib
    import time
    from datetime import datetime, timezone

    while True:
        now0 = time.time()
        if provider != "football_data":
            await asyncio.sleep(300)
            continue
        if not bool(getattr(settings, "form_refresh_enabled", True)):
            await asyncio.sleep(300)
            continue

        key = str(getattr(settings, "football_data_key", "") or "").strip()
        if not key:
            await asyncio.sleep(300)
            continue

        codes = getattr(settings, "football_data_competition_codes", {})
        if not isinstance(codes, dict) or not codes:
            await asyncio.sleep(300)
            continue

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        weekend_interval = float(getattr(settings, "form_weekend_refresh_interval_seconds", 0) or 0)
        base_interval = float(getattr(settings, "form_refresh_interval_seconds", 21600) or 21600)

        interval = base_interval
        if weekend_interval > 0 and now_dt.weekday() >= 5:
            interval = max(900.0, weekend_interval)

        last = getattr(app.state, "_form_refresh_last_unix", 0.0)
        if not isinstance(last, (int, float)):
            last = 0.0

        if (now0 - float(last)) >= float(interval):
            app.state._form_refresh_last_unix = now0
            with contextlib.suppress(Exception):
                rebuild_team_form_from_football_data(
                    codes={str(k): str(v) for k, v in codes.items()},
                    api_base_url=str(getattr(settings, "football_data_base_url", "")),
                    api_key=key,
                    season_start_utc_iso=str(getattr(settings, "fixtures_season_start_utc", "2025-08-01T00:00:00Z")),
                    season_end_utc_iso=str(getattr(settings, "fixtures_season_end_utc", "2026-06-30T23:59:59Z")),
                    form_path=str(getattr(settings, "form_path", "data/team_form.json")),
                    window=int(getattr(settings, "form_window_matches", 5)),
                )

        await asyncio.sleep(300)


async def _alpha_scheduler() -> None:
    import asyncio
    import contextlib
    import time
    from datetime import datetime, timezone

    while True:
        now0 = time.time()
        if not bool(getattr(settings, "calibration_alpha_enabled", True)):
            await asyncio.sleep(300)
            continue

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        weekend_interval = float(getattr(settings, "calibration_alpha_weekend_refresh_interval_seconds", 0) or 0)
        base_interval = float(getattr(settings, "calibration_alpha_refresh_interval_seconds", 21600) or 21600)

        interval = base_interval
        if weekend_interval > 0 and now_dt.weekday() >= 5:
            interval = max(900.0, weekend_interval)

        last = getattr(app.state, "_alpha_refresh_last_unix", 0.0)
        if not isinstance(last, (int, float)):
            last = 0.0

        if (now0 - float(last)) >= float(interval):
            app.state._alpha_refresh_last_unix = now0
            with contextlib.suppress(Exception):
                rebuild_calibration_alpha(
                    db_path=str(getattr(settings, "state_db_path", "data/forecast_state.sqlite3")),
                    out_path=str(getattr(settings, "calibration_alpha_path", "data/calibration_alpha.json")),
                    lookback_days=int(getattr(settings, "calibration_alpha_lookback_days", 60)),
                    per_league_limit=int(getattr(settings, "calibration_alpha_per_league_limit", 600)),
                    min_samples=int(getattr(settings, "calibration_alpha_min_samples", 40)),
                    market="1x2",
                )

        await asyncio.sleep(300)


async def _backtest_metrics_scheduler() -> None:
    import asyncio
    import contextlib
    import time
    from datetime import datetime, timezone

    while True:
        now0 = time.time()
        if not bool(getattr(settings, "backtest_metrics_enabled", True)):
            await asyncio.sleep(300)
            continue

        weekend_interval = float(getattr(settings, "backtest_metrics_weekend_refresh_interval_seconds", 0) or 0)
        base_interval = float(getattr(settings, "backtest_metrics_refresh_interval_seconds", 21600) or 21600)

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        interval = base_interval
        if weekend_interval > 0 and now_dt.weekday() >= 5:
            interval = max(900.0, weekend_interval)

        last = getattr(app.state, "_backtest_metrics_refresh_last_unix", 0.0)
        if not isinstance(last, (int, float)):
            last = 0.0

        if (now0 - float(last)) >= float(interval):
            app.state._backtest_metrics_refresh_last_unix = now0
            with contextlib.suppress(Exception):
                rebuild_backtest_metrics_to_file(
                    db_path=str(getattr(settings, "state_db_path", "data/forecast_state.sqlite3")),
                    out_path=str(getattr(settings, "backtest_metrics_path", "data/backtest_metrics.json")),
                    lookback_days=int(getattr(settings, "backtest_metrics_lookback_days", 60)),
                    per_league_limit=int(getattr(settings, "backtest_metrics_per_league_limit", 800)),
                    min_samples=int(getattr(settings, "backtest_metrics_min_samples", 60)),
                    market="1x2",
                    ece_bins=int(getattr(settings, "backtest_metrics_ece_bins", 10)),
                )

        await asyncio.sleep(300)


async def _backtest_trends_scheduler() -> None:
    import asyncio
    import contextlib
    import time
    from datetime import datetime, timezone

    while True:
        now0 = time.time()
        if not bool(getattr(settings, "backtest_trends_enabled", True)):
            await asyncio.sleep(300)
            continue

        weekend_interval = float(getattr(settings, "backtest_trends_weekend_refresh_interval_seconds", 0) or 0)
        base_interval = float(getattr(settings, "backtest_trends_refresh_interval_seconds", 21600) or 21600)

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        interval = base_interval
        if weekend_interval > 0 and now_dt.weekday() >= 5:
            interval = max(900.0, weekend_interval)

        last = getattr(app.state, "_backtest_trends_refresh_last_unix", 0.0)
        if not isinstance(last, (int, float)):
            last = 0.0

        if (now0 - float(last)) >= float(interval):
            app.state._backtest_trends_refresh_last_unix = now0
            with contextlib.suppress(Exception):
                rebuild_backtest_trends_to_file(
                    db_path=str(getattr(settings, "state_db_path", "data/forecast_state.sqlite3")),
                    out_path=str(getattr(settings, "backtest_trends_path", "data/backtest_trends.json")),
                    market="1x2",
                    ece_bins=int(getattr(settings, "backtest_trends_ece_bins", 10)),
                    per_league_limit_7d=int(getattr(settings, "backtest_trends_per_league_limit_7d", 400)),
                    per_league_limit_30d=int(getattr(settings, "backtest_trends_per_league_limit_30d", 800)),
                    min_samples_7d=int(getattr(settings, "backtest_trends_min_samples_7d", 25)),
                    min_samples_30d=int(getattr(settings, "backtest_trends_min_samples_30d", 60)),
                )

        await asyncio.sleep(300)


async def _decision_gate_tuning_scheduler() -> None:
    import asyncio
    import contextlib
    import time
    from datetime import datetime, timezone

    while True:
        now0 = time.time()
        if not bool(getattr(settings, "decision_gate_tuning_enabled", True)):
            await asyncio.sleep(300)
            continue

        weekend_interval = float(getattr(settings, "decision_gate_tuning_weekend_refresh_interval_seconds", 0) or 0)
        base_interval = float(getattr(settings, "decision_gate_tuning_refresh_interval_seconds", 21600) or 21600)

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        interval = base_interval
        if weekend_interval > 0 and now_dt.weekday() >= 5:
            interval = max(900.0, weekend_interval)

        last = getattr(app.state, "_decision_gate_tuning_last_unix", 0.0)
        if not isinstance(last, (int, float)):
            last = 0.0

        if (now0 - float(last)) >= float(interval):
            app.state._decision_gate_tuning_last_unix = now0
            with contextlib.suppress(Exception):
                rebuild_decision_gate_tuned(
                    backtest_metrics_path=str(getattr(settings, "backtest_metrics_path", "data/backtest_metrics.json")),
                    backtest_trends_path=str(getattr(settings, "backtest_trends_path", "data/backtest_trends.json")),
                    base_thresholds=getattr(settings, "decision_gate_thresholds", {}) or {},
                    out_path=str(getattr(settings, "decision_gate_tuned_path", "data/decision_gate_tuned.json")),
                    params=TuneParams(
                        ece_good=float(getattr(settings, "decision_gate_tuning_ece_good", 0.06) or 0.06),
                        ece_bad=float(getattr(settings, "decision_gate_tuning_ece_bad", 0.12) or 0.12),
                        logloss_good=float(getattr(settings, "decision_gate_tuning_logloss_good", 0.98) or 0.98),
                        logloss_bad=float(getattr(settings, "decision_gate_tuning_logloss_bad", 1.08) or 1.08),
                        max_delta_prob=float(getattr(settings, "decision_gate_tuning_max_delta_prob", 0.03) or 0.03),
                        max_delta_conf=float(getattr(settings, "decision_gate_tuning_max_delta_conf", 0.03) or 0.03),
                        max_delta_gap=float(getattr(settings, "decision_gate_tuning_max_delta_gap", 0.015) or 0.015),
                        min_samples=int(getattr(settings, "decision_gate_tuning_min_samples", 80) or 80),
                        trend_weight=float(getattr(settings, "decision_gate_tuning_trend_weight", 0.35) or 0.35),
                        trend_extra_prob=float(getattr(settings, "decision_gate_trend_extra_prob", 0.012) or 0.012),
                        trend_extra_conf=float(getattr(settings, "decision_gate_trend_extra_conf", 0.012) or 0.012),
                        trend_extra_gap=float(getattr(settings, "decision_gate_trend_extra_gap", 0.004) or 0.004),
                    ),
                )

        await asyncio.sleep(300)


def _in_quiet_hours(*, quiet_hours: list[int], now_utc: datetime) -> bool:
    if not isinstance(quiet_hours, list) or len(quiet_hours) != 2:
        return False
    try:
        start_h = int(quiet_hours[0])
        end_h = int(quiet_hours[1])
    except Exception:
        return False
    start_h = max(0, min(23, start_h))
    end_h = max(0, min(23, end_h))
    h = int(now_utc.hour)
    if start_h == end_h:
        return False
    if start_h < end_h:
        return start_h <= h < end_h
    return h >= start_h or h < end_h


def _success_to_risk_label(success_pct: float) -> str:
    s = float(success_pct)
    if s >= 75.0:
        return "LOW"
    if s >= 65.0:
        return "MEDIUM"
    return "HIGH"


def _market_prob(match: LiveMatchState, market: str) -> float:
    mk = str(market or "").strip().upper()
    probs = match.probabilities if isinstance(match.probabilities, dict) else {}
    if mk in {"1", "HOME", "HOME_WIN", "H"}:
        return float(probs.get("home_win", 0.0) or 0.0)
    if mk in {"X", "DRAW", "D"}:
        return float(probs.get("draw", 0.0) or 0.0)
    if mk in {"2", "AWAY", "AWAY_WIN", "A"}:
        return float(probs.get("away_win", 0.0) or 0.0)
    return 0.0


def _send_email_notification(*, subject: str, body: str) -> bool:
    if not bool(getattr(settings, "notifications_email_enabled", False)):
        return False
    host = str(getattr(settings, "notifications_email_smtp_host", "") or "").strip()
    if not host:
        return False
    port = int(getattr(settings, "notifications_email_smtp_port", 587) or 587)
    from_addr = str(getattr(settings, "notifications_email_from", "") or "").strip()
    to_addr = str(getattr(settings, "notifications_email_to", "") or "").strip()
    if not from_addr or not to_addr:
        return False
    user = str(getattr(settings, "notifications_email_smtp_user", "") or "").strip()
    password = str(getattr(settings, "notifications_email_smtp_password", "") or "").strip()

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = str(subject or "").strip()[:160]
    msg.set_content(str(body or ""))

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except Exception:
                pass
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception:
        return False


async def _notifications_scheduler(provider: str, state: AppState, hub: WebSocketHub) -> None:
    while True:
        now0 = time.time()
        interval = float(getattr(settings, "notifications_interval_seconds", 300) or 300)
        if interval < 30:
            interval = 30.0

        if not bool(getattr(settings, "notifications_enabled", False)):
            await asyncio.sleep(interval)
            continue

        prefs = await state.get_notification_preferences(user_id="default")
        if not bool(prefs.get("enabled")):
            await asyncio.sleep(interval)
            continue

        now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
        quiet_hours = prefs.get("quiet_hours")
        if isinstance(quiet_hours, list) and _in_quiet_hours(quiet_hours=quiet_hours, now_utc=now_dt):
            await asyncio.sleep(interval)
            continue

        channels = prefs.get("channels")
        if not isinstance(channels, list) or not channels:
            channels = ["push"]
        channels = [str(c).strip().lower() for c in channels if str(c).strip()]
        if not channels:
            channels = ["push"]

        max_per_day = int(prefs.get("max_per_day") or 5)
        if max_per_day <= 0:
            max_per_day = 5
        min_interval_minutes = int(prefs.get("min_interval_minutes") or 30)
        if min_interval_minutes < 0:
            min_interval_minutes = 0

        matches = await state.list_matches()
        matches_by_id = {m.match_id: m for m in matches if isinstance(getattr(m, "match_id", None), str)}

        notifications_to_send: list[tuple[str, str, dict[str, Any]]] = []

        hours = int(getattr(settings, "notifications_match_imminent_hours", 24) or 24)
        for m in matches:
            if str(getattr(m, "status", "") or "").upper() == "FINISHED":
                continue
            ku = getattr(m, "kickoff_unix", None)
            if not isinstance(ku, (int, float)):
                continue
            dt = float(ku) - float(now0)
            if dt <= 0:
                continue
            if dt > float(hours) * 3600.0:
                continue
            day_utc = time.strftime("%Y-%m-%d", time.gmtime(float(now0)))
            key = f"match_imminent:{m.match_id}:{day_utc}"
            payload = {
                "match_id": str(m.match_id),
                "championship": str(m.championship),
                "home_team": str(m.home_team),
                "away_team": str(m.away_team),
                "kickoff_unix": float(ku),
                "hours_window": int(hours),
            }
            notifications_to_send.append((key, "match_imminent", payload))

        team_success_threshold = float(getattr(settings, "notifications_team_success_threshold_pct", 75.0) or 75.0)
        ratings: dict[str, dict[str, float]] = {}
        try:
            from api_gateway.routes.insights import _read_ratings as _read_ratings_impl  # type: ignore
            from api_gateway.routes.insights import _strength_to_pct as _strength_to_pct_impl  # type: ignore
            from api_gateway.routes.insights import _clamp01 as _clamp01_impl  # type: ignore
        except Exception:
            _read_ratings_impl = None
            _strength_to_pct_impl = None
            _clamp01_impl = None

        if _read_ratings_impl is not None and _strength_to_pct_impl is not None and _clamp01_impl is not None:
            ratings = _read_ratings_impl()
            finished_by_champ: dict[str, list[tuple[float, str, str, int, int]]] = {}
            for m in matches:
                if str(getattr(m, "status", "") or "").upper() != "FINISHED":
                    continue
                if getattr(m, "kickoff_unix", None) is None:
                    continue
                meta = getattr(m, "meta", None)
                fs = None
                if isinstance(meta, dict):
                    ctx = meta.get("context") if isinstance(meta.get("context"), dict) else None
                    if isinstance(ctx, dict):
                        f0 = ctx.get("final_score")
                        if isinstance(f0, dict) and isinstance(f0.get("home"), int) and isinstance(f0.get("away"), int):
                            fs = (int(f0["home"]), int(f0["away"]))
                if fs is None:
                    continue
                finished_by_champ.setdefault(str(getattr(m, "championship", "") or ""), []).append((float(m.kickoff_unix), m.home_team, m.away_team, fs[0], fs[1]))

            for champ, strengths in ratings.items():
                games = finished_by_champ.get(champ, [])
                games.sort(key=lambda x: x[0], reverse=True)
                recent: dict[str, list[float]] = {t: [] for t in strengths.keys()}
                for _, home, away, hg, ag in games:
                    if home in recent and len(recent[home]) < 8:
                        recent[home].append(1.0 if hg > ag else (0.5 if hg == ag else 0.0))
                    if away in recent and len(recent[away]) < 8:
                        recent[away].append(1.0 if ag > hg else (0.5 if hg == ag else 0.0))
                    if all(len(v) >= 8 for v in recent.values()):
                        break

                scored: list[tuple[str, float, float, float]] = []
                for team, strength in strengths.items():
                    s_pct = float(_strength_to_pct_impl(float(strength)))
                    last = recent.get(team, [])
                    f_pct = (sum(last) / len(last)) if last else 0.5
                    success = 100.0 * (0.65 * float(_clamp01_impl(s_pct)) + 0.35 * float(_clamp01_impl(float(f_pct))))
                    success = max(0.0, min(100.0, float(success)))
                    scored.append((team, float(success), float(s_pct) * 100.0, float(f_pct) * 100.0))
                scored.sort(key=lambda x: (-x[1], x[0].lower()))
                if not scored:
                    continue
                team, success_pct, strength_pct, form_pct = scored[0]
                if float(success_pct) < float(team_success_threshold):
                    continue
                day_utc = time.strftime("%Y-%m-%d", time.gmtime(float(now0)))
                key = f"teams_to_play:{champ}:{team}:{day_utc}"
                payload = {
                    "championship": str(champ),
                    "team": str(team),
                    "success_pct": round(float(success_pct), 1),
                    "strength_pct": round(float(strength_pct), 1),
                    "form_pct": round(float(form_pct), 1),
                    "confidence_pct": round(float(success_pct), 1),
                    "risk": _success_to_risk_label(float(success_pct)),
                }
                notifications_to_send.append((key, "teams_to_play", payload))

        value_threshold = float(getattr(settings, "notifications_value_index_threshold", 10.0) or 10.0)
        odds_rows = await state.list_odds(limit=500)
        for row in odds_rows:
            mid = str(row.get("match_id") or "").strip()
            mk = str(row.get("market") or "").strip()
            odds = row.get("odds")
            if not mid or not mk or not isinstance(odds, (int, float)):
                continue
            if float(odds) <= 1.01:
                continue
            m = matches_by_id.get(mid)
            if m is None:
                continue
            if str(getattr(m, "status", "") or "").upper() == "FINISHED":
                continue
            p = _market_prob(m, mk)
            if p <= 0:
                continue
            success_pct = 100.0 * max(0.0, min(1.0, float(p)))
            implied_pct = 100.0 / float(odds)
            value_index = float(success_pct) - float(implied_pct)
            if value_index < float(value_threshold):
                continue
            if value_index >= 12.0:
                level = "HIGH"
            elif value_index >= 8.0:
                level = "MEDIUM"
            else:
                level = "LOW"
            day_utc = time.strftime("%Y-%m-%d", time.gmtime(float(now0)))
            key = f"value_pick:{mid}:{mk}:{day_utc}"
            payload = {
                "match_id": str(mid),
                "championship": str(getattr(m, "championship", "")),
                "home_team": str(getattr(m, "home_team", "")),
                "away_team": str(getattr(m, "away_team", "")),
                "kickoff_unix": float(getattr(m, "kickoff_unix", 0.0) or 0.0),
                "market": str(mk),
                "odds": float(odds),
                "implied_pct": round(float(implied_pct), 1),
                "success_pct": round(float(success_pct), 1),
                "value_index": round(float(value_index), 1),
                "value_level": str(level),
            }
            notifications_to_send.append((key, "value_pick", payload))

        for key, ntype, payload in notifications_to_send:
            notification_id = await state.insert_notification_if_new(notification_key=str(key), ntype=str(ntype), payload=dict(payload))
            for ch in channels:
                c_today, last_sent = await state.get_delivery_stats(user_id="default", channel=ch)
                if int(c_today) >= int(max_per_day):
                    continue
                if float(last_sent) > 0 and (float(now0) - float(last_sent)) < float(min_interval_minutes) * 60.0:
                    continue
                if not await state.log_delivery_if_new(user_id="default", channel=ch, notification_key=str(key), ntype=str(ntype)):
                    continue
                if ch == "push" and bool(getattr(settings, "notifications_push_enabled", True)):
                    await hub.broadcast(LiveUpdateEvent(type="notification", payload={"type": str(ntype), "key": str(key), "payload": dict(payload), "ts": float(now0)}))
                elif ch == "email":
                    subj = f"{str(ntype).replace('_', ' ').title()} · Forecast"
                    body = json.dumps(dict(payload), ensure_ascii=False, indent=2)
                    ok = await asyncio.to_thread(_send_email_notification, subject=subj, body=body)
                    if ok and isinstance(notification_id, str):
                        await state.mark_notification_email_sent(notification_id=str(notification_id))

        await asyncio.sleep(interval)


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
    if provider in {"football_data", "api_football"} and not os.getenv("VERCEL"):
        app.state.seed_task = asyncio.create_task(_seed_scheduler(provider, app.state.app_state, app.state.ws_hub))
    if provider == "football_data" and not os.getenv("VERCEL"):
        app.state.ratings_task = asyncio.create_task(_ratings_scheduler(provider))
        app.state.form_task = asyncio.create_task(_form_scheduler(provider))
    if provider in {"football_data", "api_football", "mock", "local_files"} and not os.getenv("VERCEL"):
        app.state.calibration_alpha_task = asyncio.create_task(_alpha_scheduler())
    if provider in {"football_data", "api_football", "mock", "local_files"} and not os.getenv("VERCEL"):
        app.state.backtest_metrics_task = asyncio.create_task(_backtest_metrics_scheduler())
    if provider in {"football_data", "api_football", "mock", "local_files"} and not os.getenv("VERCEL"):
        app.state.backtest_trends_task = asyncio.create_task(_backtest_trends_scheduler())
    if provider in {"football_data", "api_football", "mock", "local_files"} and not os.getenv("VERCEL"):
        app.state.decision_gate_tuning_task = asyncio.create_task(_decision_gate_tuning_scheduler())
    if provider in {"football_data", "api_football", "mock", "local_files"} and not os.getenv("VERCEL"):
        app.state.notifications_task = asyncio.create_task(_notifications_scheduler(provider, app.state.app_state, app.state.ws_hub))


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "seed_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "sim_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "ratings_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "form_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "calibration_alpha_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "backtest_metrics_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "backtest_trends_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "decision_gate_tuning_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(Exception):
            await task
    task = getattr(app.state, "notifications_task", None)
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
    app.state.data_error = None


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
    context = None
    if str(url).lower().startswith("https://"):
        cafile = _CERTIFI_CAFILE
        try:
            context = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
        except Exception:
            context = None
    with urlopen(req, timeout=30, context=context) as resp:
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
    days_back = int(getattr(settings, "fixtures_refresh_days_back", 3) or 3)
    raw_ahead = getattr(settings, "fixtures_refresh_days_ahead", 0)
    days_ahead = int(raw_ahead) if isinstance(raw_ahead, int) and int(raw_ahead) > 0 else int(getattr(settings, "fixtures_days_ahead", 90) or 90)
    from_day = (now_dt - timedelta(days=max(0, days_back))).date()
    to_day = (now_dt + timedelta(days=max(7, days_ahead))).date()
    headers = {"x-apisports-key": settings.api_football_key}
    ttl_seconds = float(getattr(settings, "fixtures_refresh_cache_ttl_seconds", 600) or 600)

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
        cache_key = f"af_fixtures:refresh:{league_id}:{season}:{from_day.isoformat()}:{to_day.isoformat()}"
        cached = await state.get_cache_json(cache_key)
        try:
            if cached is not None:
                payload = cached
            else:
                payload = _http_get_json(url, headers=headers)
                await state.set_cache_json(cache_key, payload, ttl_seconds)
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
    else:
        app.state.data_error = None


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
    disabled_until = getattr(app.state, "_football_data_disabled_until", 0.0)
    if isinstance(disabled_until, (int, float)) and float(disabled_until) > now0:
        return
    days_back = int(getattr(settings, "fixtures_refresh_days_back", 3) or 3)
    raw_ahead = getattr(settings, "fixtures_refresh_days_ahead", 0)
    days_ahead = int(raw_ahead) if isinstance(raw_ahead, int) and int(raw_ahead) > 0 else int(getattr(settings, "fixtures_days_ahead", 90) or 90)
    from_day = (now_dt - timedelta(days=max(0, days_back))).date()
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
        cache_key = f"fd_matches:refresh:{code}:{from_day.isoformat()}:{to_day.isoformat()}"
        ttl_seconds = float(getattr(settings, "fixtures_refresh_cache_ttl_seconds", 600) or 600)
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
                elif code0 == 400:
                    last_error = f"football_data_http_400:{snippet}" if snippet else "football_data_http_400"
                    low = snippet.lower()
                    if "token" in low and "invalid" in low:
                        app.state._football_data_disabled_until = time.time() + 86400.0
                        await _seed_from_mock(state, hub)
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
    else:
        app.state.data_error = None


async def _seed_from_football_data_season(state: AppState, hub: WebSocketHub) -> None:
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

    now0 = time.time()
    now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)
    until = getattr(app.state, "_football_data_rate_limited_until", 0.0)
    if isinstance(until, (int, float)) and float(until) > now0:
        app.state.data_error = "football_data_http_429:rate_limited"
        return
    disabled_until = getattr(app.state, "_football_data_disabled_until", 0.0)
    if isinstance(disabled_until, (int, float)) and float(disabled_until) > now0:
        return

    start_dt = _parse_utc_iso(str(getattr(settings, "fixtures_season_start_utc", "") or "")) or datetime(2025, 8, 1, tzinfo=timezone.utc)
    end_dt = _parse_utc_iso(str(getattr(settings, "fixtures_season_end_utc", "") or "")) or datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    from_day = start_dt.date()
    to_day = end_dt.date()

    days_back = int(getattr(settings, "fixtures_refresh_days_back", 3) or 3)
    raw_ahead = getattr(settings, "fixtures_refresh_days_ahead", 0)
    days_ahead = int(raw_ahead) if isinstance(raw_ahead, int) and int(raw_ahead) > 0 else int(getattr(settings, "fixtures_days_ahead", 90) or 90)
    refresh_from_unix = (now_dt - timedelta(days=max(0, days_back))).timestamp()
    refresh_to_unix = (now_dt + timedelta(days=max(7, days_ahead))).timestamp()

    headers = {"X-Auth-Token": key, "Accept": "application/json", "User-Agent": str(getattr(settings, "app_name", "Forecast Master System API"))}
    ttl_seconds = float(getattr(settings, "fixtures_season_cache_ttl_seconds", 43200) or 43200)

    total_upserted = 0
    last_error: str | None = None

    comps = list((settings.football_data_competition_codes or {}).items())
    max_n = int(getattr(settings, "football_data_max_competitions_per_seed", len(comps) or 1) or (len(comps) or 1))
    if max_n < 1:
        max_n = 1
    if max_n > len(comps):
        max_n = len(comps)
    selected = comps[:max_n]

    for champ, code in selected:
        alpha = await state.get_calibration_alpha(champ)
        qs = urlencode({"dateFrom": from_day.isoformat(), "dateTo": to_day.isoformat()})
        url = f"{settings.football_data_base_url.rstrip('/')}/competitions/{code}/matches?{qs}"
        cache_key = f"fd_matches:season:{code}:{from_day.isoformat()}:{to_day.isoformat()}"
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
                if code0 in {401, 403}:
                    last_error = f"football_data_http_{code0}:{snippet}" if snippet else f"football_data_http_{code0}"
                    app.state.data_error = last_error
                    return
                if code0 == 400:
                    last_error = f"football_data_http_400:{snippet}" if snippet else "football_data_http_400"
                    low = snippet.lower()
                    if "token" in low and "invalid" in low:
                        app.state._football_data_disabled_until = time.time() + 86400.0
                        await _seed_from_mock(state, hub)
                        return
                if code0 == 429:
                    last_error = "football_data_http_429:rate_limited"
                    app.state._football_data_rate_limited_until = time.time() + 300.0
                    if cached is None:
                        app.state.data_error = last_error
                        return
                    payload = cached
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

        items = payload.get("matches") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            last_error = "football_data_bad_response"
            if settings.real_data_only:
                app.state.data_error = last_error
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

            should_predict = False
            if isinstance(kickoff_unix, (int, float)):
                ku = float(kickoff_unix)
                should_predict = refresh_from_unix <= ku <= refresh_to_unix

            if should_predict:
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
            else:
                existing = await state.get_match(match_id)
                probs = {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
                explain: dict[str, Any] = {"seed": "season"}
                if existing is not None:
                    if isinstance(existing.probabilities, dict) and existing.probabilities:
                        probs = dict(existing.probabilities)
                    if isinstance(existing.meta, dict):
                        ex0 = existing.meta.get("explain")
                        if isinstance(ex0, dict) and ex0:
                            explain = dict(ex0)
                m.update(probabilities=probs, meta={"context": context0, "explain": explain})

            m.update(next_update_unix=orchestrator.compute_next_update_unix(m, now_unix=now0))
            await state.upsert_match(m)
            total_upserted += 1
            if should_predict:
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

    if total_upserted == 0 and last_error:
        app.state.data_error = last_error
    elif total_upserted > 0:
        app.state.data_error = None


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
