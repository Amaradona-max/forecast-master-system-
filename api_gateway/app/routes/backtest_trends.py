from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from api_gateway.app.config import settings

router = APIRouter()


@router.get("/backtest-trends")
def get_backtest_trends() -> dict[str, Any]:
    path = Path(str(getattr(settings, "backtest_trends_path", "data/backtest_trends.json")))
    if not path.exists():
        return {"ok": False, "error": "backtest_trends_missing", "championships": {}}

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid_json", "championships": {}}
        champs = data.get("championships")
        if not isinstance(champs, dict):
            champs = {}
        return {
            "ok": True,
            "meta": data.get("meta") or {},
            "generated_at_unix": data.get("generated_at_unix"),
            "championships": champs,
        }
    except Exception:
        return {"ok": False, "error": "read_failed", "championships": {}}
