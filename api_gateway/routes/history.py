from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
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


class PredictionHistoryItem(BaseModel):
    prediction_id: str
    match_id: str
    championship: str
    home_team: str
    away_team: str
    market: str
    predicted_pick: str
    predicted_prob: float
    confidence: float
    predicted_at_unix: float
    kickoff_unix: float | None = None
    final_outcome: str | None = None
    correct: bool | None = None
    roi_simulated: float | None = None
    resolved_at_unix: float | None = None


class PredictionHistoryResponse(BaseModel):
    generated_at_utc: datetime
    items: list[PredictionHistoryItem] = Field(default_factory=list)


class TrackBucket(BaseModel):
    n: int
    accuracy: float
    roi_avg: float


class TrackSummary(BaseModel):
    n: int
    accuracy: float
    roi_total: float
    roi_avg: float
    by_confidence: dict[str, TrackBucket] = Field(default_factory=dict)


class TrackPoint(BaseModel):
    date_utc: datetime
    n: int
    accuracy: float
    roi_total: float


class TrackRecordResponse(BaseModel):
    generated_at_utc: datetime
    championship: str
    days: int
    summary: TrackSummary
    points: list[TrackPoint] = Field(default_factory=list)


def _bucket(conf: float) -> str:
    c = float(conf)
    if c >= 0.75:
        return "high"
    if c >= 0.60:
        return "medium"
    return "low"


@router.get("/api/v1/history/predictions", response_model=PredictionHistoryResponse)
async def prediction_history(
    request: Request,
    championship: str = "all",
    resolved_only: bool = True,
    days: int = 120,
    limit: int = 800,
) -> PredictionHistoryResponse:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    d = int(days)
    if d < 1:
        d = 1
    if d > 3650:
        d = 3650
    since_unix = datetime.now(timezone.utc).timestamp() - float(d) * 86400.0
    rows = await state.list_prediction_history(
        championship=str(championship),
        resolved_only=bool(resolved_only),
        since_unix=float(since_unix),
        limit=int(limit),
    )
    items = [PredictionHistoryItem(**r) for r in rows if isinstance(r, dict)]
    return PredictionHistoryResponse(generated_at_utc=datetime.now(timezone.utc), items=items)


@router.get("/api/v1/history/track-record", response_model=TrackRecordResponse)
async def track_record(request: Request, response: Response, championship: str = "all", days: int = 120) -> TrackRecordResponse:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    d = int(days)
    if d < 1:
        d = 1
    if d > 3650:
        d = 3650
    now_unix = datetime.now(timezone.utc).timestamp()
    since_unix = now_unix - float(d) * 86400.0
    rows = await state.list_resolved_predictions_since(championship=str(championship), since_unix=float(since_unix))

    n = 0
    correct = 0
    roi_total = 0.0
    buckets: dict[str, dict[str, float]] = {"high": {"n": 0, "c": 0, "roi": 0.0}, "medium": {"n": 0, "c": 0, "roi": 0.0}, "low": {"n": 0, "c": 0, "roi": 0.0}}
    by_day: dict[str, dict[str, float]] = {}

    for r in rows:
        if not isinstance(r, dict):
            continue
        n += 1
        is_correct = bool(r.get("correct"))
        correct += 1 if is_correct else 0
        roi = float(r.get("roi_simulated") or 0.0)
        roi_total += roi

        b = _bucket(float(r.get("confidence") or 0.0))
        buckets[b]["n"] += 1
        buckets[b]["c"] += 1 if is_correct else 0
        buckets[b]["roi"] += roi

        ts = float(r.get("resolved_at_unix") or 0.0)
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        if day not in by_day:
            by_day[day] = {"n": 0, "c": 0, "roi": 0.0}
        by_day[day]["n"] += 1
        by_day[day]["c"] += 1 if is_correct else 0
        by_day[day]["roi"] += roi

    acc = (float(correct) / float(n)) if n else 0.0
    roi_avg = (float(roi_total) / float(n)) if n else 0.0

    by_conf: dict[str, TrackBucket] = {}
    for k, v in buckets.items():
        nn = int(v["n"])
        cc = int(v["c"])
        rr = float(v["roi"])
        by_conf[k] = TrackBucket(n=nn, accuracy=(float(cc) / float(nn)) if nn else 0.0, roi_avg=(float(rr) / float(nn)) if nn else 0.0)

    points: list[TrackPoint] = []
    for day, v in sorted(by_day.items(), key=lambda x: x[0]):
        nn = int(v["n"])
        cc = int(v["c"])
        rr = float(v["roi"])
        dt = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        points.append(TrackPoint(date_utc=dt, n=nn, accuracy=(float(cc) / float(nn)) if nn else 0.0, roi_total=float(rr)))

    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=3600"
    response.headers["Vary"] = "x-tenant-id, Accept-Encoding"
    return TrackRecordResponse(
        generated_at_utc=datetime.now(timezone.utc),
        championship=str(championship),
        days=int(d),
        summary=TrackSummary(n=int(n), accuracy=float(acc), roi_total=float(roi_total), roi_avg=float(roi_avg), by_confidence=by_conf),
        points=points,
    )
