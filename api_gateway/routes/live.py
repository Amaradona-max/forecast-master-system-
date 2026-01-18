from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api_gateway.app.schemas import LiveProbabilitiesResponse


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


@router.get("/api/v1/live/{match_id}/probabilities", response_model=LiveProbabilitiesResponse)
async def get_live_probabilities(match_id: str, request: Request) -> LiveProbabilitiesResponse:
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
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
