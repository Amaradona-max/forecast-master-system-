from __future__ import annotations

import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _brier(p: float, y: int) -> float:
    d = float(p) - float(y)
    return d * d


def _log_loss(p: float, y: int) -> float:
    p2 = _clamp(float(p), 1e-12, 1.0 - 1e-12)
    if int(y) == 1:
        return -math.log(p2)
    return -math.log(1.0 - p2)


def _ece(*, pairs: list[tuple[float, int]], bins: int) -> tuple[float, list[dict[str, Any]]]:
    n = len(pairs)
    if n <= 0:
        return 0.0, []
    b = int(bins)
    if b < 2:
        b = 2
    if b > 50:
        b = 50

    cnt = [0 for _ in range(b)]
    sum_p = [0.0 for _ in range(b)]
    sum_y = [0.0 for _ in range(b)]

    for p, y in pairs:
        p2 = _clamp(float(p), 0.0, 1.0)
        idx = int(p2 * b)
        if idx >= b:
            idx = b - 1
        if idx < 0:
            idx = 0
        cnt[idx] += 1
        sum_p[idx] += p2
        sum_y[idx] += float(int(y))

    out_bins: list[dict[str, Any]] = []
    ece = 0.0
    for i in range(b):
        c = cnt[i]
        lo = float(i) / float(b)
        hi = float(i + 1) / float(b)
        if c <= 0:
            out_bins.append({"bin_lo": lo, "bin_hi": hi, "count": 0, "predicted_avg": 0.0, "observed_rate": 0.0})
            continue
        avg_p = float(sum_p[i]) / float(c)
        avg_y = float(sum_y[i]) / float(c)
        ece += abs(avg_p - avg_y) * (float(c) / float(n))
        out_bins.append({"bin_lo": lo, "bin_hi": hi, "count": int(c), "predicted_avg": float(avg_p), "observed_rate": float(avg_y)})

    return float(ece), out_bins


def compute_backtest_metrics(
    *,
    db_path: str,
    lookback_days: int = 365,
    per_league_limit: int = 2000,
    min_samples: int = 40,
    market: str = "1x2",
    ece_bins: int = 10,
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
              AND correct IS NOT NULL
              AND resolved_at_unix IS NOT NULL
              AND resolved_at_unix >= ?
              AND predicted_prob IS NOT NULL
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
        try:
            prob = float(r["predicted_prob"])
        except Exception:
            continue
        if not math.isfinite(prob):
            continue
        corr = int(r["correct"] or 0)
        corr = 1 if corr == 1 else 0
        prob = _clamp(prob, 0.0, 1.0)
        by.setdefault(champ, []).append((float(prob), int(corr)))

    leagues: dict[str, dict[str, Any]] = {}
    for champ, pairs in by.items():
        pairs = pairs[: int(per_league_limit)]
        n = len(pairs)
        if n < int(min_samples):
            continue

        acc = sum(y for _, y in pairs) / float(n)
        avg_p = sum(p for p, _ in pairs) / float(n)
        brier = sum(_brier(p, y) for p, y in pairs) / float(n)
        logloss = sum(_log_loss(p, y) for p, y in pairs) / float(n)
        ece, bins_out = _ece(pairs=pairs, bins=int(ece_bins))

        leagues[str(champ)] = {
            "n": int(n),
            "accuracy": float(acc),
            "avg_p": float(avg_p),
            "brier": float(brier),
            "log_loss": float(logloss),
            "ece": float(ece),
            "bins": bins_out,
        }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_unix": float(now0),
        "meta": {
            "model": "backtest_metrics_v1",
            "lookback_days": int(lookback_days),
            "per_league_limit": int(per_league_limit),
            "min_samples": int(min_samples),
            "market": str(market),
            "ece_bins": int(ece_bins),
        },
        "leagues": {k: v for k, v in sorted(leagues.items(), key=lambda kv: kv[0])},
    }
    return payload


def write_metrics_file(*, out_path: str, payload: dict[str, Any]) -> None:
    op = Path(out_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(op)


def rebuild_backtest_metrics_to_file(
    *,
    db_path: str,
    out_path: str,
    lookback_days: int,
    per_league_limit: int,
    min_samples: int,
    market: str,
    ece_bins: int,
) -> dict[str, Any] | None:
    payload = compute_backtest_metrics(
        db_path=db_path,
        lookback_days=lookback_days,
        per_league_limit=per_league_limit,
        min_samples=min_samples,
        market=market,
        ece_bins=ece_bins,
    )
    if not isinstance(payload, dict):
        return None
    write_metrics_file(out_path=out_path, payload=payload)
    return payload

