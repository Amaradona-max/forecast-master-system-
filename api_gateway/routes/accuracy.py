from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from api_gateway.app.schemas import (
    CalibrationBin,
    CalibrationMetricsResponse,
    CalibrationSummaryResponse,
    CalibrationWindowMetrics,
    SeasonAccuracyPoint,
    SeasonAccuracyResponse,
)


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


def _calibration_bins(rows: list[tuple[dict[str, float], str]], bins: int = 10) -> tuple[list[CalibrationBin], float]:
    if not rows or bins <= 1:
        return ([], 0.0)
    bins = max(2, min(50, int(bins)))

    sums_p = [0.0 for _ in range(bins)]
    sums_y = [0.0 for _ in range(bins)]
    counts = [0 for _ in range(bins)]

    for probs, outcome in rows:
        p1 = float(probs.get("home_win", 0.0))
        px = float(probs.get("draw", 0.0))
        p2 = float(probs.get("away_win", 0.0))
        pick = "home_win" if (p1 >= px and p1 >= p2) else "draw" if (px >= p1 and px >= p2) else "away_win"
        p_pick = float(probs.get(pick, 0.0))
        if p_pick < 0.0:
            p_pick = 0.0
        if p_pick > 1.0:
            p_pick = 1.0
        y = 1.0 if pick == outcome else 0.0

        i = int(min(bins - 1, math.floor(p_pick * bins)))
        sums_p[i] += p_pick
        sums_y[i] += y
        counts[i] += 1

    total = sum(counts)
    if total <= 0:
        return ([], 0.0)

    out_bins: list[CalibrationBin] = []
    ece = 0.0
    for i in range(bins):
        c = counts[i]
        lo = float(i) / float(bins)
        hi = float(i + 1) / float(bins)
        if c <= 0:
            out_bins.append(CalibrationBin(bin_lo=lo, bin_hi=hi, predicted_avg=0.0, observed_rate=0.0, count=0))
            continue
        p_avg = sums_p[i] / float(c)
        y_avg = sums_y[i] / float(c)
        out_bins.append(CalibrationBin(bin_lo=lo, bin_hi=hi, predicted_avg=float(p_avg), observed_rate=float(y_avg), count=int(c)))
        ece += abs(p_avg - y_avg) * (float(c) / float(total))

    return (out_bins, float(ece))


def _latest_finished_rows(matches: list[object], championship: str, window: int | None) -> list[tuple[dict[str, float], str]]:
    champ = str(championship or "").strip() or "serie_a"
    filtered: list[object] = []
    for m in matches:
        if getattr(m, "status", None) != "FINISHED":
            continue
        if getattr(m, "championship", None) != champ:
            continue
        if not isinstance(getattr(m, "kickoff_unix", None), (int, float)):
            continue
        if _extract_result(m) is None:
            continue
        filtered.append(m)

    filtered.sort(key=lambda x: float(getattr(x, "kickoff_unix", 0.0) or 0.0), reverse=True)
    if isinstance(window, int) and window > 0:
        filtered = filtered[: int(window)]

    out: list[tuple[dict[str, float], str]] = []
    for m in filtered:
        extracted = _extract_result(m)
        if extracted is None:
            continue
        out.append(extracted)
    return out


def _build_calibration_metrics(*, matches: list[object], championship: str, window: int | None) -> CalibrationWindowMetrics:
    rows = _latest_finished_rows(matches, championship, window)
    brier, log_loss, _acc = _metrics(rows)
    bins, ece = _calibration_bins(rows, bins=10)
    win: int | str = "season" if window is None else int(window)
    return CalibrationWindowMetrics(window=win, n=int(len(rows)), log_loss=float(log_loss), brier=float(brier), ece=float(ece), bins=bins)


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


@router.get("/api/v1/accuracy/calibration", response_model=CalibrationMetricsResponse)
async def calibration_metrics(request: Request, championship: str = "serie_a", window: int = 200) -> CalibrationMetricsResponse:
    state = request.app.state.app_state
    matches = await state.list_matches()
    win = max(1, min(10000, int(window)))
    metrics = _build_calibration_metrics(matches=matches, championship=championship, window=win)
    return CalibrationMetricsResponse(championship=championship, metrics=metrics)


@router.get("/api/v1/accuracy/calibration-summary", response_model=CalibrationSummaryResponse)
async def calibration_summary(request: Request, championship: str = "serie_a") -> CalibrationSummaryResponse:
    state = request.app.state.app_state
    matches = await state.list_matches()
    last_50 = _build_calibration_metrics(matches=matches, championship=championship, window=50)
    last_200 = _build_calibration_metrics(matches=matches, championship=championship, window=200)
    season = _build_calibration_metrics(matches=matches, championship=championship, window=None)
    return CalibrationSummaryResponse(championship=championship, last_50=last_50, last_200=last_200, season_to_date=season)
