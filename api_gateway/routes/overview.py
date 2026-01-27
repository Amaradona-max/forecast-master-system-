from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

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


def _tenant_id_from_request(request: Request) -> str:
    tid = request.headers.get("x-tenant-id")
    if isinstance(tid, str) and tid.strip():
        return tid.strip().lower()
    qp = request.query_params.get("tenant") or request.query_params.get("tenant_id")
    if isinstance(qp, str) and qp.strip():
        return qp.strip().lower()
    return "default"


def _country_from_request(request: Request) -> str | None:
    for k in ("cf-ipcountry", "x-country", "x-geo-country"):
        v = request.headers.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return None


def _apply_region_policy(request: Request, compliance: dict[str, Any]) -> None:
    if not isinstance(compliance, dict):
        return
    cc = _country_from_request(request)
    allow = compliance.get("allowed_countries")
    block = compliance.get("blocked_countries")
    allow_list = [str(x).strip().upper() for x in (allow if isinstance(allow, list) else []) if str(x).strip()]
    block_list = [str(x).strip().upper() for x in (block if isinstance(block, list) else []) if str(x).strip()]
    if cc is None:
        return
    if block_list and cc in set(block_list):
        raise HTTPException(status_code=451, detail="region_blocked")
    if allow_list and cc not in set(allow_list):
        raise HTTPException(status_code=451, detail="region_not_allowed")


def _normalize_confidence_label(v: Any) -> str:
    s = str(v or "").strip().upper()
    if s in {"HIGH", "ALTA", "A"}:
        return "HIGH"
    if s in {"MEDIUM", "MEDIA", "M"}:
        return "MEDIUM"
    return "LOW"


class TenantBranding(BaseModel):
    app_name: str = "Forecast Master System"
    tagline: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None


class TenantFilters(BaseModel):
    visible_championships: list[str] = Field(default_factory=list)
    active_markets: list[str] = Field(default_factory=lambda: ["1X2", "OVER_2_5", "BTTS"])
    min_confidence: str = "LOW"


class TenantCompliance(BaseModel):
    disclaimer_text: str = ""
    educational_only: bool = False
    allowed_countries: list[str] = Field(default_factory=list)
    blocked_countries: list[str] = Field(default_factory=list)


class TenantFeatures(BaseModel):
    disabled_profiles: list[str] = Field(default_factory=list)


class TenantConfig(BaseModel):
    tenant_id: str = "default"
    branding: TenantBranding = Field(default_factory=TenantBranding)
    filters: TenantFilters = Field(default_factory=TenantFilters)
    compliance: TenantCompliance = Field(default_factory=TenantCompliance)
    features: TenantFeatures = Field(default_factory=TenantFeatures)
    updated_at_unix: float = 0.0


class TenantBrandingUpdate(BaseModel):
    app_name: str | None = None
    tagline: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None


class TenantFiltersUpdate(BaseModel):
    visible_championships: list[str] | None = None
    active_markets: list[str] | None = None
    min_confidence: str | None = None


class TenantComplianceUpdate(BaseModel):
    disclaimer_text: str | None = None
    educational_only: bool | None = None
    allowed_countries: list[str] | None = None
    blocked_countries: list[str] | None = None


class TenantFeaturesUpdate(BaseModel):
    disabled_profiles: list[str] | None = None


class TenantConfigUpdate(BaseModel):
    branding: TenantBrandingUpdate | None = None
    filters: TenantFiltersUpdate | None = None
    compliance: TenantComplianceUpdate | None = None
    features: TenantFeaturesUpdate | None = None


def _effective_data_provider() -> str:
    provider = str(getattr(settings, "data_provider", "") or "").strip()
    if provider == "api_football":
        if not bool(getattr(settings, "api_football_key", None)) and bool(getattr(settings, "football_data_key", None)):
            return "football_data"
    return provider


def _supported_championships(provider: str) -> list[str]:
    order = ["serie_a", "premier_league", "la_liga", "bundesliga", "eliteserien"]
    if provider == "football_data":
        keys = list((settings.football_data_competition_codes or {}).keys())
    elif provider in {"api_football", "local_files"}:
        keys = list((settings.api_football_league_ids or {}).keys())
    else:
        keys = list(order)

    keys = [k for k in keys if k in order]
    out = [c for c in order if c in keys]
    for c in keys:
        if c not in out:
            out.append(c)
    return out


def _apply_tenant_championship_filter(*, champs: list[str], tenant_filters: dict[str, Any]) -> list[str]:
    raw = tenant_filters.get("visible_championships") if isinstance(tenant_filters, dict) else None
    allow = [str(x).strip().lower() for x in (raw if isinstance(raw, list) else []) if str(x).strip()]
    if not allow:
        return champs
    allow_set = set(allow)
    out = [c for c in champs if str(c).strip().lower() in allow_set]
    return out if out else champs


def _tenant_config_from_state_row(*, row: dict[str, Any], tenant_id: str) -> TenantConfig:
    cfg0 = row.get("config") if isinstance(row, dict) else None
    cfg = cfg0 if isinstance(cfg0, dict) else {}
    branding = cfg.get("branding") if isinstance(cfg.get("branding"), dict) else {}
    filters = cfg.get("filters") if isinstance(cfg.get("filters"), dict) else {}
    compliance = cfg.get("compliance") if isinstance(cfg.get("compliance"), dict) else {}
    features = cfg.get("features") if isinstance(cfg.get("features"), dict) else {}

    active_markets_raw = filters.get("active_markets")
    active_markets = [str(x).strip().upper() for x in (active_markets_raw if isinstance(active_markets_raw, list) else []) if str(x).strip()]
    if not active_markets:
        active_markets = ["1X2", "OVER_2_5", "BTTS"]

    visible_champs_raw = filters.get("visible_championships")
    visible_champs = [str(x).strip().lower() for x in (visible_champs_raw if isinstance(visible_champs_raw, list) else []) if str(x).strip()]

    disabled_raw = features.get("disabled_profiles")
    disabled_profiles = [str(x).strip().upper() for x in (disabled_raw if isinstance(disabled_raw, list) else []) if str(x).strip()]
    allowed_profiles = {"PRUDENT", "BALANCED", "AGGRESSIVE"}
    disabled_profiles = [p for p in disabled_profiles if p in allowed_profiles]

    tc = TenantConfig(
        tenant_id=str(tenant_id or "default"),
        branding=TenantBranding(
            app_name=str(branding.get("app_name") or "Forecast Master System"),
            tagline=str(branding.get("tagline")).strip() if isinstance(branding.get("tagline"), str) else None,
            logo_url=str(branding.get("logo_url")).strip() if isinstance(branding.get("logo_url"), str) else None,
            primary_color=str(branding.get("primary_color")).strip() if isinstance(branding.get("primary_color"), str) else None,
        ),
        filters=TenantFilters(
            visible_championships=visible_champs,
            active_markets=active_markets,
            min_confidence=_normalize_confidence_label(filters.get("min_confidence", "LOW")),
        ),
        compliance=TenantCompliance(
            disclaimer_text=str(compliance.get("disclaimer_text") or ""),
            educational_only=bool(compliance.get("educational_only", False)),
            allowed_countries=[str(x).strip().upper() for x in (compliance.get("allowed_countries") if isinstance(compliance.get("allowed_countries"), list) else []) if str(x).strip()],
            blocked_countries=[str(x).strip().upper() for x in (compliance.get("blocked_countries") if isinstance(compliance.get("blocked_countries"), list) else []) if str(x).strip()],
        ),
        features=TenantFeatures(disabled_profiles=disabled_profiles),
        updated_at_unix=float(row.get("updated_at_unix") or 0.0) if isinstance(row, dict) else 0.0,
    )
    return tc


@router.get("/api/v1/tenant/config", response_model=TenantConfig)
async def get_tenant_config(request: Request, response: Response) -> TenantConfig:
    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    tenant_id = _tenant_id_from_request(request)
    state = request.app.state.app_state
    row = await state.get_tenant_config(tenant_id=tenant_id)
    tc = _tenant_config_from_state_row(row=row, tenant_id=tenant_id)
    _apply_region_policy(request, tc.compliance.model_dump())
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=3600"
    response.headers["Vary"] = "x-tenant-id"
    return tc


@router.put("/api/v1/tenant/config", response_model=TenantConfig)
async def put_tenant_config(req: TenantConfigUpdate, request: Request) -> TenantConfig:
    token = str(getattr(settings, "admin_token", "") or "").strip()
    if not token:
        raise HTTPException(status_code=403, detail="admin_token_not_configured")
    provided = request.headers.get("x-admin-token")
    if not isinstance(provided, str) or provided.strip() != token:
        raise HTTPException(status_code=403, detail="admin_forbidden")

    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    tenant_id = _tenant_id_from_request(request)
    state = request.app.state.app_state
    cur_row = await state.get_tenant_config(tenant_id=tenant_id)
    cur_cfg0 = cur_row.get("config") if isinstance(cur_row, dict) else None
    cur_cfg: dict[str, Any] = cur_cfg0 if isinstance(cur_cfg0, dict) else {}

    next_cfg: dict[str, Any] = dict(cur_cfg)
    if req.branding is not None:
        b0 = next_cfg.get("branding")
        b: dict[str, Any] = b0 if isinstance(b0, dict) else {}
        up = req.branding
        if up.app_name is not None:
            b["app_name"] = str(up.app_name)
        if up.tagline is not None:
            b["tagline"] = str(up.tagline)
        if up.logo_url is not None:
            b["logo_url"] = str(up.logo_url)
        if up.primary_color is not None:
            b["primary_color"] = str(up.primary_color)
        next_cfg["branding"] = b

    if req.filters is not None:
        f0 = next_cfg.get("filters")
        f: dict[str, Any] = f0 if isinstance(f0, dict) else {}
        up = req.filters
        if up.visible_championships is not None:
            f["visible_championships"] = [str(x).strip().lower() for x in (up.visible_championships or []) if str(x).strip()]
        if up.active_markets is not None:
            f["active_markets"] = [str(x).strip().upper() for x in (up.active_markets or []) if str(x).strip()]
        if up.min_confidence is not None:
            f["min_confidence"] = _normalize_confidence_label(up.min_confidence)
        next_cfg["filters"] = f

    if req.compliance is not None:
        c0 = next_cfg.get("compliance")
        c: dict[str, Any] = c0 if isinstance(c0, dict) else {}
        up = req.compliance
        if up.disclaimer_text is not None:
            c["disclaimer_text"] = str(up.disclaimer_text)
        if up.educational_only is not None:
            c["educational_only"] = bool(up.educational_only)
        if up.allowed_countries is not None:
            c["allowed_countries"] = [str(x).strip().upper() for x in (up.allowed_countries or []) if str(x).strip()]
        if up.blocked_countries is not None:
            c["blocked_countries"] = [str(x).strip().upper() for x in (up.blocked_countries or []) if str(x).strip()]
        next_cfg["compliance"] = c

    if req.features is not None:
        fe0 = next_cfg.get("features")
        fe: dict[str, Any] = fe0 if isinstance(fe0, dict) else {}
        up = req.features
        if up.disabled_profiles is not None:
            allowed_profiles = {"PRUDENT", "BALANCED", "AGGRESSIVE"}
            vals = [str(x).strip().upper() for x in (up.disabled_profiles or []) if str(x).strip()]
            fe["disabled_profiles"] = [p for p in vals if p in allowed_profiles]
        next_cfg["features"] = fe

    saved = await state.upsert_tenant_config(tenant_id=tenant_id, config=next_cfg)
    tc = _tenant_config_from_state_row(row=saved, tenant_id=tenant_id)
    _apply_region_policy(request, tc.compliance.model_dump())
    return tc


def _top_score(probs: dict[str, float]) -> float:
    p1 = float(probs.get("home_win", 0.0) or 0.0)
    px = float(probs.get("draw", 0.0) or 0.0)
    p2 = float(probs.get("away_win", 0.0) or 0.0)
    v = sorted([max(p1, 0.0), max(px, 0.0), max(p2, 0.0)], reverse=True)
    best = v[0] if v else 0.0
    second = v[1] if len(v) > 1 else 0.0
    margin = max(best - second, 0.0)
    denom = math.log(3.0)
    ent = 0.0
    for p in (best, second, v[2] if len(v) > 2 else 0.0):
        ent += -p * math.log(max(p, 1e-12))
    ent_n = (ent / denom) if denom > 0 else 1.0
    certainty = 1.0 - min(max(ent_n, 0.0), 1.0)
    score = best + (0.40 * margin) + (0.15 * certainty)
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return float(score)


class SystemStatusResponse(BaseModel):
    data_provider: str
    real_data_only: bool
    data_error: str | None = None
    matches_loaded: int
    api_football_key_present: bool
    api_football_leagues_configured: int
    api_football_seasons_configured: int
    football_data_key_present: bool
    football_data_competitions_configured: int
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
        data_provider=_effective_data_provider(),
        real_data_only=settings.real_data_only,
        data_error=getattr(request.app.state, "data_error", None),
        matches_loaded=len(matches),
        api_football_key_present=bool(settings.api_football_key),
        api_football_leagues_configured=len(settings.api_football_league_ids or {}),
        api_football_seasons_configured=len(settings.api_football_season_years or {}),
        football_data_key_present=bool(settings.football_data_key),
        football_data_competitions_configured=len(settings.football_data_competition_codes or {}),
        now_utc=datetime.now(timezone.utc),
    )


@router.get("/api/v1/overview/championships", response_model=ChampionshipsOverviewResponse)
async def championships_overview(request: Request, response: Response) -> ChampionshipsOverviewResponse:
    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    if not hasattr(request.app.state, "ws_hub"):
        request.app.state.ws_hub = WebSocketHub()
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    tenant_compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, tenant_compliance)
    now_unix0 = datetime.now(timezone.utc).timestamp()
    provider = _effective_data_provider()
    cache_ttl = 5.0
    cache_key = f"{tenant_id}:{provider}:{int(settings.real_data_only)}"
    cache_store = getattr(request.app.state, "_overview_cache", None)
    if not isinstance(cache_store, dict):
        cache_store = {}
        request.app.state._overview_cache = cache_store
    cached = cache_store.get(cache_key) if isinstance(cache_store, dict) else None
    if isinstance(cached, dict):
        cached_ts = cached.get("ts")
        cached_payload = cached.get("payload")
        if isinstance(cached_ts, (int, float)) and (now_unix0 - float(cached_ts)) <= cache_ttl and cached_payload is not None:
            response.headers["Cache-Control"] = "public, max-age=5, s-maxage=30, stale-while-revalidate=300"
            response.headers["Vary"] = "x-tenant-id"
            return cached_payload
    matches = await state.list_matches()
    champs = _supported_championships(provider)
    tenant_filters = tenant_cfg.get("filters") if isinstance(tenant_cfg.get("filters"), dict) else {}
    champs = _apply_tenant_championship_filter(champs=champs, tenant_filters=tenant_filters)
    err = getattr(request.app.state, "data_error", None)
    if provider == "football_data" and err == "football_data_http_429:rate_limited":
        until = getattr(request.app.state, "_football_data_rate_limited_until", 0.0)
        if isinstance(until, (int, float)) and float(until) <= datetime.now(timezone.utc).timestamp():
            request.app.state.data_error = None
            err = None
    missing_champs = []
    if matches and champs:
        present = {m.championship for m in matches}
        missing_champs = [c for c in champs if c not in present]

    now_unix0 = datetime.now(timezone.utc).timestamp()
    if err is None:
        last_refresh = getattr(request.app.state, "_refresh_seed_attempted_unix", 0.0)
        if not isinstance(last_refresh, (int, float)):
            last_refresh = 0.0
        refresh_interval = float(getattr(settings, "fixtures_refresh_interval_seconds", 600) or 600)
        if provider in {"local_files", "mock"}:
            refresh_interval = 60.0
        refresh_due = (now_unix0 - float(last_refresh)) >= refresh_interval

        last_season = getattr(request.app.state, "_season_seed_attempted_unix", 0.0)
        if not isinstance(last_season, (int, float)):
            last_season = 0.0
        season_interval = float(getattr(settings, "fixtures_season_interval_seconds", 86400) or 86400)
        season_due = (now_unix0 - float(last_season)) >= season_interval

        if provider == "football_data" and (not matches or missing_champs) and season_due:
            request.app.state._season_seed_attempted_unix = now_unix0
            try:
                from api_gateway.main import _seed_from_football_data_season  # type: ignore

                await _seed_from_football_data_season(request.app.state.app_state, request.app.state.ws_hub)
            except Exception:
                pass
            matches = await state.list_matches()

        if (not matches or missing_champs or refresh_due) and refresh_due:
            request.app.state._refresh_seed_attempted_unix = now_unix0
            try:
                if provider == "api_football":
                    from api_gateway.main import _seed_from_api_football  # type: ignore

                    await _seed_from_api_football(request.app.state.app_state, request.app.state.ws_hub)
                elif provider == "football_data":
                    from api_gateway.main import _seed_from_football_data  # type: ignore

                    await _seed_from_football_data(request.app.state.app_state, request.app.state.ws_hub)
                elif provider == "local_files":
                    from api_gateway.main import _seed_from_local_files  # type: ignore

                    await _seed_from_local_files(request.app.state.app_state, request.app.state.ws_hub)
                elif provider == "mock":
                    from api_gateway.main import _seed_from_mock  # type: ignore

                    await _seed_from_mock(request.app.state.app_state, request.app.state.ws_hub)
            except Exception:
                pass
            matches = await state.list_matches()
    now_unix = datetime.now(timezone.utc).timestamp()
    predictions_start_unix = datetime(2025, 8, 1, tzinfo=timezone.utc).timestamp() if settings.real_data_only else 0.0
    if provider == "api_football" and not matches:
        detail = getattr(request.app.state, "data_error", None) or "api_football_no_matches"
        raise HTTPException(status_code=503, detail=str(detail))
    if provider == "football_data" and not matches:
        detail = getattr(request.app.state, "data_error", None) or "football_data_no_matches"
        if str(detail) == "football_data_http_429:rate_limited":
            return ChampionshipsOverviewResponse(generated_at_utc=datetime.now(timezone.utc), championships=[])
        raise HTTPException(status_code=503, detail=str(detail))
    if settings.real_data_only and getattr(request.app.state, "data_error", None):
        if str(getattr(request.app.state, "data_error", "")) == "football_data_http_429:rate_limited":
            return ChampionshipsOverviewResponse(generated_at_utc=datetime.now(timezone.utc), championships=[])
        raise HTTPException(status_code=503, detail=str(request.app.state.data_error))
    if settings.real_data_only and not matches:
        raise HTTPException(status_code=503, detail="real_data_not_loaded")

    by_champ: dict[str, list] = {}
    for m in matches:
        by_champ.setdefault(m.championship, []).append(m)

    payload: list[ChampionshipOverview] = []
    for champ in champs:
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
            conf = _top_score(probs)
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
        thirty_days_ago = now_unix - (30 * 86400)
        finished = sorted(
            [
                m
                for m in mapped
                if m.status == "FINISHED" and (m.kickoff_unix is not None) and (m.kickoff_unix >= thirty_days_ago)
            ],
            key=lambda x: (x.kickoff_unix or 0.0, x.match_id),
            reverse=True,
        )[:50]

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

    response.headers["Cache-Control"] = "public, max-age=5, s-maxage=30, stale-while-revalidate=300"
    response.headers["Vary"] = "x-tenant-id"
    out = ChampionshipsOverviewResponse(generated_at_utc=datetime.now(timezone.utc), championships=payload)
    cache_store[cache_key] = {"ts": now_unix, "payload": out}
    return out
