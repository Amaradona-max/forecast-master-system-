from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AlphaRow:
    championship: str
    alpha: float
    n: int
    avg_p: float
    acc: float
    overconfidence: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _compute_alpha(avg_p: float, acc: float) -> float:
    """
    Heuristica semplice e robusta:
    - Se avg_p (media prob) >> accuracy reale => modello overconfident => alpha > 0
    - Se avg_p <= accuracy => niente smorzamento => alpha ~ 0

    alpha è limitato a [0, 0.35] come nel tuo calibratore.
    """
    over = avg_p - acc
    if not math.isfinite(over) or over <= 0:
        return 0.0
    a = over * 0.8
    return float(_clamp(a, 0.0, 0.35))


def rebuild_calibration_alpha(
    *,
    db_path: str,
    out_path: str,
    lookback_days: int = 60,
    per_league_limit: int = 600,
    min_samples: int = 40,
    market: str = "1x2",
) -> dict[str, Any] | None:
    """
    Legge predictions_history e calcola alpha per championship usando:
    - predicted_prob (probabilità pick scelto)
    - correct (0/1) risolto quando abbiamo final_outcome

    Usa solo righe:
    - final_outcome NOT NULL
    - predicted_prob > 0
    - market == '1x2'
    - resolved_at_unix recente (lookback)
    """
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
        prob = float(r["predicted_prob"] or 0.0)
        corr = int(r["correct"] or 0)
        by.setdefault(champ, []).append((prob, corr))

    out: dict[str, AlphaRow] = {}
    for champ, pairs in by.items():
        pairs = pairs[: int(per_league_limit)]
        if len(pairs) < int(min_samples):
            continue
        avg_p = sum(x[0] for x in pairs) / len(pairs)
        acc = sum(x[1] for x in pairs) / len(pairs)
        alpha = _compute_alpha(avg_p, acc)
        out[champ] = AlphaRow(
            championship=champ,
            alpha=float(alpha),
            n=int(len(pairs)),
            avg_p=float(avg_p),
            acc=float(acc),
            overconfidence=float(avg_p - acc),
        )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_unix": float(now0),
        "meta": {
            "model": "alpha_inseason_v1",
            "lookback_days": int(lookback_days),
            "per_league_limit": int(per_league_limit),
            "min_samples": int(min_samples),
            "market": str(market),
        },
        "championships": {
            k: {
                "alpha": v.alpha,
                "n": v.n,
                "avg_p": v.avg_p,
                "acc": v.acc,
                "overconfidence": v.overconfidence,
            }
            for k, v in sorted(out.items(), key=lambda kv: kv[0])
        },
    }

    op = Path(out_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    tmp = op.with_name(op.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(op)

    return payload
