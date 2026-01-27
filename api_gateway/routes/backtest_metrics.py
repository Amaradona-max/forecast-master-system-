from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response

from api_gateway.app.settings import settings


router = APIRouter()


def _read_backtest_metrics() -> dict[str, Any]:
    path = Path(str(getattr(settings, "backtest_metrics_path", "data/backtest_metrics.json")))
    if not path.exists():
        return {"ok": False, "error": "backtest_metrics_missing", "championships": {}}

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid_json", "championships": {}}
        champs0 = data.get("championships")
        champs = champs0 if isinstance(champs0, dict) else None
        if champs is None:
            leagues0 = data.get("leagues")
            champs = leagues0 if isinstance(leagues0, dict) else {}
        return {
            "ok": True,
            "meta": data.get("meta") or {},
            "generated_at_unix": data.get("generated_at_unix"),
            "championships": champs,
        }
    except Exception:
        return {"ok": False, "error": "read_failed", "championships": {}}


@router.get("/v1/backtest-metrics")
def get_backtest_metrics(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=900, stale-while-revalidate=86400"
    response.headers["Vary"] = "Accept-Encoding"
    return _read_backtest_metrics()


@router.get("/backtest-metrics")
def get_backtest_metrics_compat(response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "public, max-age=300, s-maxage=900, stale-while-revalidate=86400"
    response.headers["Vary"] = "Accept-Encoding"
    return _read_backtest_metrics()
