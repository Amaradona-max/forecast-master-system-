from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from api_gateway.app.schemas import SeasonAccuracyPoint, SeasonAccuracyResponse


router = APIRouter()

def _safe_float(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _extract_result(m: object) -> tuple[dict[str, float], str] | None:
    probs = getattr(m, "probabilities", None)
    if not isinstance(probs, dict):
        return None

    ctx = None
    meta = getattr(m, "meta", None)
    if isinstance(meta, dict):
        x = meta.get("context")
        if isinstance(x, dict):
            ctx = x
    if not isinstance(ctx, dict):
        return None

    final_score = ctx.get("final_score")
    if not isinstance(final_score, dict):
        return None
    hg = final_score.get("home")
    ag = final_score.get("away")
    if not isinstance(hg, int) or not isinstance(ag, int):
        return None

    p1 = _safe_float(probs.get("home_win")) or 0.0
    px = _safe_float(probs.get("draw")) or 0.0
    p2 = _safe_float(probs.get("away_win")) or 0.0
    s = max(p1, 0.0) + max(px, 0.0) + max(p2, 0.0)
    if s <= 0:
        p1, px, p2 = 1 / 3, 1 / 3, 1 / 3
    else:
        p1, px, p2 = max(p1, 0.0) / s, max(px, 0.0) / s, max(p2, 0.0) / s

    if hg > ag:
        outcome = "home_win"
    elif hg == ag:
        outcome = "draw"
    else:
        outcome = "away_win"

    return ({"home_win": p1, "draw": px, "away_win": p2}, outcome)


def _metrics(rows: list[tuple[dict[str, float], str]]) -> tuple[float, float, float]:
    if not rows:
        return (0.0, 0.0, 0.0)

    brier_sum = 0.0
    ll_sum = 0.0
    correct = 0
    for probs, outcome in rows:
        o1, ox, o2 = (1.0, 0.0, 0.0) if outcome == "home_win" else (0.0, 1.0, 0.0) if outcome == "draw" else (0.0, 0.0, 1.0)
        p1 = float(probs.get("home_win", 0.0))
        px = float(probs.get("draw", 0.0))
        p2 = float(probs.get("away_win", 0.0))
        brier_sum += ((p1 - o1) ** 2 + (px - ox) ** 2 + (p2 - o2) ** 2) / 3.0

        p_true = float(probs.get(outcome, 0.0))
        ll_sum += -math.log(max(p_true, 1e-12))

        pick = "home_win" if (p1 >= px and p1 >= p2) else "draw" if (px >= p1 and px >= p2) else "away_win"
        if pick == outcome:
            correct += 1

    n = float(len(rows))
    return (brier_sum / n, ll_sum / n, correct / n)


@router.get("/api/v1/accuracy/season-progress", response_model=SeasonAccuracyResponse)
async def season_progress(request: Request, championship: str = "all") -> SeasonAccuracyResponse:
    now = datetime.now(timezone.utc)
    state = request.app.state.app_state
    matches = await state.list_matches()
    points: list[SeasonAccuracyPoint] = []
    prev = (0.0, 0.0, 0.0)
    for i in range(14, -1, -1):
        dt = now - timedelta(days=i)
        day_start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp()
        day_end = day_start + 86400.0

        rows: list[tuple[dict[str, float], str]] = []
        for m in matches:
            champ = getattr(m, "championship", None)
            if not isinstance(champ, str):
                continue
            if championship != "all" and champ != championship:
                continue
            if getattr(m, "status", None) != "FINISHED":
                continue
            ku = getattr(m, "kickoff_unix", None)
            if not isinstance(ku, (int, float)):
                continue
            if not (day_start <= float(ku) < day_end):
                continue
            extracted = _extract_result(m)
            if extracted is None:
                continue
            rows.append(extracted)

        brier, log_loss, acc = _metrics(rows)
        if not rows:
            brier, log_loss, acc = prev
        else:
            prev = (brier, log_loss, acc)

        points.append(
            SeasonAccuracyPoint(
                date_utc=dt,
                brier=float(brier),
                log_loss=float(log_loss),
                roc_auc=float(acc),
                roi_simulated=0.0,
            )
        )
    return SeasonAccuracyResponse(championship=championship, points=points)
