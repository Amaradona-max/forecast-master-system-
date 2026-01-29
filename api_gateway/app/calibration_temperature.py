from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LABELS = ("home_win", "draw", "away_win")


@dataclass(frozen=True)
class TempRow:
    championship: str
    temperature: float
    n: int
    nll: float


def _safe_probs(p: dict[str, float]) -> list[float]:
    vals = [float(p.get(k, 0.0) or 0.0) for k in LABELS]
    s = sum(max(0.0, x) for x in vals)
    if s <= 0:
        return [1 / 3, 1 / 3, 1 / 3]
    out = [max(0.0, x) / s for x in vals]
    eps = 1e-12
    out = [max(eps, x) for x in out]
    s2 = sum(out)
    return [x / s2 for x in out]


def apply_temperature(probs: dict[str, float], T: float) -> dict[str, float]:
    """
    Temperature scaling su probabilità (equivalente a dividere i logits):
    p_i' ∝ p_i^(1/T)
    - T > 1 => smorza (meno overconfident)
    - T < 1 => rende più "sharp"
    """
    t = float(T)
    if not math.isfinite(t) or t <= 0:
        return probs
    p = _safe_probs(probs)
    power = 1.0 / t
    q = [x**power for x in p]
    s = sum(q)
    if s <= 0:
        q = [1 / 3, 1 / 3, 1 / 3]
    else:
        q = [x / s for x in q]
    return {LABELS[0]: q[0], LABELS[1]: q[1], LABELS[2]: q[2]}


def _nll_one(p: list[float], y_idx: int) -> float:
    eps = 1e-12
    return -math.log(max(eps, p[y_idx]))


def rebuild_calibration_temperature(
    *,
    db_path: str,
    out_path: str,
    lookback_days: int = 60,
    per_league_limit: int = 800,
    min_samples: int = 60,
    market: str = "1x2",
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
            SELECT championship, probabilities_json, final_outcome, resolved_at_unix
            FROM predictions_history
            WHERE
              UPPER(market) = UPPER(?)
              AND final_outcome IS NOT NULL
              AND resolved_at_unix IS NOT NULL
              AND resolved_at_unix >= ?
              AND probabilities_json IS NOT NULL
            ORDER BY resolved_at_unix DESC
            """,
            (str(market), float(since)),
        ).fetchall()
    finally:
        con.close()

    by: dict[str, list[tuple[dict[str, float], str]]] = {}
    for r in rows:
        champ = str(r["championship"] or "").strip()
        if not champ:
            continue
        try:
            probs = json.loads(str(r["probabilities_json"]))
            if not isinstance(probs, dict):
                continue
            probs = {str(k): float(v) for k, v in probs.items()}
        except Exception:
            continue
        outcome = str(r["final_outcome"] or "").strip()
        if outcome not in LABELS:
            continue
        by.setdefault(champ, []).append((probs, outcome))

    out_rows: dict[str, TempRow] = {}

    # grid search robusto (poco costo, alta stabilità)
    T_grid = [0.7, 0.85, 1.0, 1.15, 1.35, 1.6, 1.9, 2.2]

    for champ, pairs in by.items():
        pairs = pairs[: int(per_league_limit)]
        if len(pairs) < int(min_samples):
            continue

        best_T = 1.0
        best_nll = float("inf")

        for T in T_grid:
            nll = 0.0
            ok = 0
            for probs, outc in pairs:
                p_cal = apply_temperature(probs, T)
                p_vec = _safe_probs(p_cal)
                y = LABELS.index(outc)
                nll += _nll_one(p_vec, y)
                ok += 1
            if ok <= 0:
                continue
            nll /= ok
            if math.isfinite(nll) and nll < best_nll:
                best_nll = float(nll)
                best_T = float(T)

        out_rows[champ] = TempRow(championship=champ, temperature=float(best_T), n=int(len(pairs)), nll=float(best_nll))

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_unix": float(now0),
        "meta": {
            "model": "temperature_scaling_multiclass_v1",
            "lookback_days": int(lookback_days),
            "per_league_limit": int(per_league_limit),
            "min_samples": int(min_samples),
            "market": str(market),
            "grid": T_grid,
        },
        "championships": {
            k: {"temperature": v.temperature, "n": v.n, "nll": v.nll}
            for k, v in sorted(out_rows.items(), key=lambda kv: kv[0])
        },
    }

    op = Path(out_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(op)
    return payload