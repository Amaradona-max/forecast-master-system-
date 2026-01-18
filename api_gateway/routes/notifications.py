from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field


router = APIRouter()


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


@router.get("/api/v1/notifications/settings", response_model=NotificationSettings)
async def get_notification_settings(request: Request) -> NotificationSettings:
    state = request.app.state.app_state
    uid = _user_id_from_request(request)
    prefs = await state.get_notification_preferences(user_id=uid)
    return NotificationSettings(**prefs)


@router.put("/api/v1/notifications/settings", response_model=NotificationSettings)
async def put_notification_settings(req: NotificationSettingsUpdate, request: Request) -> NotificationSettings:
    state = request.app.state.app_state
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
    items = await state.list_notifications(limit=int(limit))
    return NotificationHistoryResponse(items=items)

