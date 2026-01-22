from __future__ import annotations

import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    if v != v:
        return 0.0
    return max(0.0, min(1.0, v))


def _safe_log(x: float, eps: float = 1e-12) -> float:
    return math.log(max(float(eps), float(x)))


def _ece_from_bins(pairs: Iterable[tuple[float, int]], n_bins: int = 10) -> float:
    bins = [{"n": 0, "sum_p": 0.0, "sum_y": 0.0} for _ in range(n_bins)]
    for p, y in pairs:
        p = _clamp01(p)
        y = 1.0 if int(y) == 1 else 0.0
        idx = min(n_bins - 1, max(0, int(p * n_bins)))
        b = bins[idx]
        b["n"] += 1
        b["sum_p"] += float(p)
        b["sum_y"] += float(y)

    total = sum(b["n"] for b in bins)
    if total <= 0:
        return 0.0

    ece = 0.0
    for b in bins:
        if b["n"] <= 0:
            continue
        avg_p = b["sum_p"] / b["n"]
        acc = b["sum_y"] / b["n"]
        ece += (b["n"] / total) * abs(avg_p - acc)
    return float(ece)


def _compute_metrics_from_pairs(pairs: list[tuple[float, int]], ece_bins: int) -> dict[str, float]:
    n = len(pairs)
    if n <= 0:
        return {"n": 0, "accuracy": 0.0, "brier": 0.0, "logloss": 0.0, "ece": 0.0, "avg_pred_prob": 0.0}

    acc = sum(y for _, y in pairs) / n
    avg_p = sum(p for p, _ in pairs) / n
    brier = sum((p - float(y)) ** 2 for p, y in pairs) / n
    logloss = -sum((float(y) * _safe_log(p) + (1.0 - float(y)) * _safe_log(1.0 - p)) for p, y in pairs) / n
    ece = _ece_from_bins(pairs, n_bins=int(ece_bins))

    return {
        "n": float(n),
        "accuracy": float(acc),
        "avg_pred_prob": float(avg_p),
        "brier": float(brier),
        "logloss": float(logloss),
        "ece": float(ece),
    }


def compute_window_metrics(
    *,
    db_path: str,
    lookback_days: int,
    per_league_limit: int,
    market: str,
    ece_bins: int,
) -> dict[str, Any] | None:
    now0 = time.time()
    since = now0 - float(lookback_days) * 86400.0
    p = Path(db_path)
    if not p.exists():
        return None

    con = sqlite3.connect(str(p))
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT championship, predicted_prob, correct, resolved_at_unix
            FROM predictions_history
            WHERE
              UPPER(market) = UPPER(?)
              AND final_outcome IS NOT NULL
              AND resolved_at_unix IS NOT NULL
              AND resolved_at_unix >= ?
              AND predicted_prob IS NOT NULL
              AND predicted_prob > 0
              AND correct IS NOT NULL
            ORDER BY resolved_at_unix DESC
            """,
            (str(market), float(since)),
        ).fetchall()
    finally:
        con.close()

    by: dict[str, list[tuple[float, int]]] = {}
    for r in rows:
        champ = str(r["championship"] or "").strip()
        if not champ:
            continue
        prob = _clamp01(float(r["predicted_prob"] or 0.0))
        corr = int(r["correct"] or 0)
        corr = 1 if corr == 1 else 0
        by.setdefault(champ, []).append((prob, corr))

    out: dict[str, Any] = {}
    for champ, pairs in by.items():
        pairs = pairs[: int(per_league_limit)]
        out[str(champ)] = _compute_metrics_from_pairs(pairs, ece_bins=int(ece_bins))

    return {
        "generated_at_unix": float(now0),
        "lookback_days": int(lookback_days),
        "market": str(market),
        "championships": out,
    }


def rebuild_backtest_trends_to_file(
    *,
    db_path: str,
    out_path: str,
    market: str = "1x2",
    ece_bins: int = 10,
    per_league_limit_7d: int = 400,
    per_league_limit_30d: int = 800,
    min_samples_7d: int = 25,
    min_samples_30d: int = 60,
) -> dict[str, Any] | None:
    w7 = compute_window_metrics(
        db_path=db_path,
        lookback_days=7,
        per_league_limit=per_league_limit_7d,
        market=market,
        ece_bins=ece_bins,
    )
    w30 = compute_window_metrics(
        db_path=db_path,
        lookback_days=30,
        per_league_limit=per_league_limit_30d,
        market=market,
        ece_bins=ece_bins,
    )
    if not isinstance(w7, dict) or not isinstance(w30, dict):
        return None

    c7 = w7.get("championships") or {}
    c30 = w30.get("championships") or {}
    if not isinstance(c7, dict) or not isinstance(c30, dict):
        return None

    champs_out: dict[str, Any] = {}
    keys = set(c7.keys()) | set(c30.keys())
    for champ in sorted(keys):
        r7 = c7.get(champ) if isinstance(c7.get(champ), dict) else {}
        r30 = c30.get(champ) if isinstance(c30.get(champ), dict) else {}

        n7 = int(float(r7.get("n", 0) or 0))
        n30 = int(float(r30.get("n", 0) or 0))

        if n7 < int(min_samples_7d) or n30 < int(min_samples_30d):
            champs_out[champ] = {
                "ok": False,
                "n7": n7,
                "n30": n30,
            }
            continue

        acc7 = float(r7.get("accuracy", 0.0) or 0.0)
        acc30 = float(r30.get("accuracy", 0.0) or 0.0)
        ece7 = float(r7.get("ece", 0.0) or 0.0)
        ece30 = float(r30.get("ece", 0.0) or 0.0)

        d_acc = acc7 - acc30
        d_ece = ece7 - ece30

        champs_out[champ] = {
            "ok": True,
            "n7": n7,
            "n30": n30,
            "acc7": acc7,
            "acc30": acc30,
            "ece7": ece7,
            "ece30": ece30,
            "delta_accuracy": d_acc,
            "delta_ece": d_ece,
            "window7": r7,
            "window30": r30,
        }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_unix": float(time.time()),
        "meta": {
            "model": "backtest_trends_7v30_v1",
            "market": str(market),
            "ece_bins": int(ece_bins),
            "per_league_limit_7d": int(per_league_limit_7d),
            "per_league_limit_30d": int(per_league_limit_30d),
            "min_samples_7d": int(min_samples_7d),
            "min_samples_30d": int(min_samples_30d),
        },
        "championships": champs_out,
    }

    op = Path(out_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(op)
    return payload

