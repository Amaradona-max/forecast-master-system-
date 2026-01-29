from __future__ import annotations

import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LABELS = ("home_win", "draw", "away_win")


def _psi(a: list[float], b: list[float], eps: float = 1e-9) -> float:
    s = 0.0
    for x, y in zip(a, b, strict=False):
        x = max(eps, float(x))
        y = max(eps, float(y))
        s += (x - y) * math.log(x / y)
    return float(s)


def _normalize_counts(counts: dict[str, int], keys: tuple[str, ...]) -> list[float]:
    tot = sum(max(0, int(counts.get(k, 0))) for k in keys)
    if tot <= 0:
        return [1.0 / len(keys)] * len(keys)
    return [float(counts.get(k, 0)) / float(tot) for k in keys]


def _bin_prob(p: float) -> int:
    # bins enterprise (stabili)
    # 0-50, 50-60, 60-70, 70-80, 80-90, 90-100
    edges = [0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for i, e in enumerate(edges):
        if p < e:
            return i
    return len(edges) - 1


def rebuild_drift_status(
    *,
    db_path: str,
    out_path: str,
    recent_days: int = 30,
    baseline_days: int = 365,
    min_samples: int = 120,
    market: str = "1x2",
    psi_warn: float = 0.15,
    psi_high: float = 0.25,
) -> dict[str, Any] | None:
    now0 = time.time()
    p = Path(db_path)
    if not p.exists():
        return None

    recent_since = now0 - float(recent_days) * 86400.0
    base_since = now0 - float(baseline_days) * 86400.0

    con = sqlite3.connect(str(p))
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT championship, predicted_prob, final_outcome, resolved_at_unix
            FROM predictions_history
            WHERE
              UPPER(market) = UPPER(?)
              AND final_outcome IS NOT NULL
              AND resolved_at_unix IS NOT NULL
              AND resolved_at_unix >= ?
              AND predicted_prob IS NOT NULL
            ORDER BY resolved_at_unix DESC
            """,
            (str(market), float(base_since)),
        ).fetchall()
    finally:
        con.close()

    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        champ = str(r["championship"] or "").strip()
        if not champ:
            continue
        outc = str(r["final_outcome"] or "").strip()
        if outc not in LABELS:
            continue
        ts = float(r["resolved_at_unix"] or 0.0)
        pprob = float(r["predicted_prob"] or 0.0)
        if pprob < 0:
            pprob = 0.0
        if pprob > 1:
            pprob = 1.0

        bucket = by.setdefault(
            champ,
            {
                "recent_out": {k: 0 for k in LABELS},
                "base_out": {k: 0 for k in LABELS},
                "recent_bins": [0] * 6,
                "base_bins": [0] * 6,
                "n_recent": 0,
                "n_base": 0,
            },
        )

        bucket["base_out"][outc] += 1
        bucket["base_bins"][_bin_prob(pprob)] += 1
        bucket["n_base"] += 1

        if ts >= recent_since:
            bucket["recent_out"][outc] += 1
            bucket["recent_bins"][_bin_prob(pprob)] += 1
            bucket["n_recent"] += 1

    champs_payload: dict[str, Any] = {}

    for champ, b in by.items():
        n_recent = int(b["n_recent"])
        n_base = int(b["n_base"])
        if n_recent < int(min_samples) or n_base < int(min_samples):
            continue

        recent_out = _normalize_counts(b["recent_out"], LABELS)
        base_out = _normalize_counts(b["base_out"], LABELS)
        psi_out = _psi(recent_out, base_out)

        # bins
        def _norm_bins(arr: list[int]) -> list[float]:
            tot = sum(arr)
            if tot <= 0:
                return [1 / len(arr)] * len(arr)
            return [x / tot for x in arr]

        psi_bins = _psi(_norm_bins(b["recent_bins"]), _norm_bins(b["base_bins"]))

        level = "ok"
        flags: list[str] = []
        if psi_out >= psi_high or psi_bins >= psi_high:
            level = "high"
            flags.append("high_drift")
        elif psi_out >= psi_warn or psi_bins >= psi_warn:
            level = "warn"
            flags.append("drift_warning")

        champs_payload[champ] = {
            "level": level,
            "flags": flags,
            "psi": {"outcome": float(psi_out), "confidence_bins": float(psi_bins)},
            "samples": {"recent": n_recent, "baseline": n_base},
        }

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_unix": float(now0),
        "meta": {
            "market": str(market),
            "recent_days": int(recent_days),
            "baseline_days": int(baseline_days),
            "min_samples": int(min_samples),
            "psi_warn": float(psi_warn),
            "psi_high": float(psi_high),
        },
        "championships": champs_payload,
    }

    op = Path(out_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(op)
    return payload