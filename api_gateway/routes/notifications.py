from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


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


def _user_id_from_request(request: Request) -> str:
    uid = request.headers.get("x-user-id")
    if not isinstance(uid, str):
        return "default"
    uid = uid.strip()
    return uid if uid else "default"


class NotificationSettings(BaseModel):
    user_id: str = "default"
    enabled: bool = False
    channels: list[str] = Field(default_factory=lambda: ["push"])
    quiet_hours: list[int] = Field(default_factory=lambda: [22, 8])
    max_per_day: int = 5
    min_interval_minutes: int = 30
    updated_at_unix: float = 0.0


class NotificationSettingsUpdate(BaseModel):
    enabled: bool
    channels: list[str] = Field(default_factory=list)
    quiet_hours: list[int] = Field(default_factory=list)
    max_per_day: int = 5
    min_interval_minutes: int = 30


class NotificationHistoryResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)


class UserProfile(BaseModel):
    user_id: str = "default"
    profile: str = "BALANCED"
    bankroll_reference: float = 100.0
    preferred_markets: list[str] = Field(default_factory=lambda: ["1x2", "over_2_5", "btts"])
    preferred_championships: list[str] = Field(default_factory=list)
    notifications_enabled: bool = False
    notifications_min_confidence: str = "MEDIUM"
    updated_at_unix: float = 0.0


class UserProfileUpdate(BaseModel):
    profile: str | None = None
    bankroll_reference: float | None = None
    preferred_markets: list[str] | None = None
    preferred_championships: list[str] | None = None
    notifications_enabled: bool | None = None
    notifications_min_confidence: str | None = None


def _profile_defaults(profile: str) -> dict:
    p = str(profile or "").strip().upper()
    if p in {"PRUDENTE", "PRUDENT", "CONSERVATIVE"}:
        return {
            "profile": "PRUDENT",
            "notifications_min_confidence": "HIGH",
        }
    if p in {"AGGRESSIVO", "AGGRESSIVE"}:
        return {
            "profile": "AGGRESSIVE",
            "notifications_min_confidence": "LOW",
        }
    return {
        "profile": "BALANCED",
        "notifications_min_confidence": "MEDIUM",
    }


def _get_profiles_store(state: object) -> dict[str, dict]:
    store = getattr(state, "_user_profiles", None)
    if not isinstance(store, dict):
        store = {}
        setattr(state, "_user_profiles", store)
    return store


@router.get("/api/v1/notifications/settings", response_model=NotificationSettings)
async def get_notification_settings(request: Request) -> NotificationSettings:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    uid = _user_id_from_request(request)
    prefs = await state.get_notification_preferences(user_id=uid)
    return NotificationSettings(**prefs)


@router.put("/api/v1/notifications/settings", response_model=NotificationSettings)
async def put_notification_settings(req: NotificationSettingsUpdate, request: Request) -> NotificationSettings:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    uid = _user_id_from_request(request)
    prefs = await state.upsert_notification_preferences(
        user_id=uid,
        enabled=bool(req.enabled),
        channels=list(req.channels or []),
        quiet_hours=list(req.quiet_hours or []),
        max_per_day=int(req.max_per_day),
        min_interval_minutes=int(req.min_interval_minutes),
    )
    return NotificationSettings(**prefs)


@router.get("/api/v1/notifications/history", response_model=NotificationHistoryResponse)
async def notifications_history(request: Request, limit: int = 50) -> NotificationHistoryResponse:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    items = await state.list_notifications(limit=int(limit))
    return NotificationHistoryResponse(items=items)


@router.get("/api/v1/user/profile", response_model=UserProfile)
async def get_user_profile(request: Request) -> UserProfile:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    uid = _user_id_from_request(request)
    store = _get_profiles_store(state)
    raw = store.get(uid)
    if isinstance(raw, dict) and raw:
        return UserProfile(**raw)
    base = _profile_defaults("BALANCED")
    now_unix = float(time.time())
    data = {
        "user_id": uid,
        **base,
        "bankroll_reference": 100.0,
        "preferred_markets": ["1x2", "over_2_5", "btts"],
        "preferred_championships": [],
        "notifications_enabled": False,
        "updated_at_unix": now_unix,
    }
    store[uid] = dict(data)
    return UserProfile(**data)


@router.put("/api/v1/user/profile", response_model=UserProfile)
async def put_user_profile(req: UserProfileUpdate, request: Request) -> UserProfile:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    uid = _user_id_from_request(request)
    store = _get_profiles_store(state)
    cur = store.get(uid) if isinstance(store.get(uid), dict) else {}
    profile_in = req.profile if req.profile is not None else cur.get("profile", "BALANCED")
    base = _profile_defaults(str(profile_in))
    now_unix = float(time.time())

    bankroll_reference = req.bankroll_reference if req.bankroll_reference is not None else cur.get("bankroll_reference", 100.0)
    try:
        br = float(bankroll_reference)
    except Exception:
        br = 100.0
    if br < 0.0:
        br = 0.0
    if br > 1_000_000.0:
        br = 1_000_000.0

    markets = req.preferred_markets if req.preferred_markets is not None else cur.get("preferred_markets", ["1x2", "over_2_5", "btts"])
    champs = req.preferred_championships if req.preferred_championships is not None else cur.get("preferred_championships", [])
    if not isinstance(markets, list):
        markets = ["1x2", "over_2_5", "btts"]
    if not isinstance(champs, list):
        champs = []

    notifications_enabled = req.notifications_enabled if req.notifications_enabled is not None else cur.get("notifications_enabled", False)
    notifications_min_confidence = (
        req.notifications_min_confidence if req.notifications_min_confidence is not None else cur.get("notifications_min_confidence", base["notifications_min_confidence"])
    )

    data = {
        "user_id": uid,
        **base,
        "bankroll_reference": float(br),
        "preferred_markets": [str(x).strip().lower() for x in markets if str(x).strip()],
        "preferred_championships": [str(x).strip().lower() for x in champs if str(x).strip()],
        "notifications_enabled": bool(notifications_enabled),
        "notifications_min_confidence": str(notifications_min_confidence or base["notifications_min_confidence"]).strip().upper() or base["notifications_min_confidence"],
        "updated_at_unix": now_unix,
    }
    store[uid] = dict(data)
    return UserProfile(**data)
