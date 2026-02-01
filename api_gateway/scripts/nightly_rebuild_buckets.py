#!/usr/bin/env python3
"""Nightly job: rebuild similarity buckets with Bayesian smoothing (anti-noise).

This script performs:
1) Join prediction_events.jsonl + match_results.jsonl -> backtest_events.jsonl
2) Build similarity_buckets.json (bucket: championship|tier|chaos_bucket|fragility_level)
   using Beta prior smoothing to prevent '100% accuracy' on tiny samples.

Inputs (paths can be overridden with env vars):
- PRED_LOG     default api_gateway/data/prediction_events.jsonl
- RESULTS      default api_gateway/data/match_results.jsonl
- BACKTEST_OUT default api_gateway/data/backtest_events.jsonl
- BUCKETS_OUT  default api_gateway/data/similarity_buckets.json

Config:
- MIN_SAMPLES  default 50
- PRIOR_ALPHA  default 3
- PRIOR_BETA   default 3

Run:
  python api_gateway/scripts/nightly_rebuild_buckets.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                yield obj
        except Exception:
            continue


def load_results(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return {}
    # JSON array/object
    if text.startswith("[") or text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return {str(r.get("match_id")): r for r in obj if isinstance(r, dict) and r.get("match_id")}
            if isinstance(obj, dict):
                if obj.get("match_id"):
                    return {str(obj["match_id"]): obj}
                recs = obj.get("records")
                if isinstance(recs, list):
                    return {str(r.get("match_id")): r for r in recs if isinstance(r, dict) and r.get("match_id")}
        except Exception:
            pass
    # JSONL fallback
    return {str(r.get("match_id")): r for r in iter_jsonl(path) if r.get("match_id")}


def norm_outcome(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip().lower()
    if s in {"home_win", "1", "h", "home"}:
        return "home_win"
    if s in {"draw", "x", "d"}:
        return "draw"
    if s in {"away_win", "2", "a", "away"}:
        return "away_win"
    return None


def outcome_from_goals(r: Dict[str, Any]) -> Optional[str]:
    hg = r.get("home_goals", r.get("hg"))
    ag = r.get("away_goals", r.get("ag"))
    try:
        hg = int(hg)
        ag = int(ag)
    except Exception:
        return None
    if hg > ag:
        return "home_win"
    if hg < ag:
        return "away_win"
    return "draw"


def bucketize_chaos(x: Any) -> str:
    try:
        v = float(x)
    except Exception:
        return "na"
    if v >= 85:
        return "vhigh"
    if v >= 70:
        return "high"
    if v >= 55:
        return "mid"
    return "low"


def norm_fragility(level: Any) -> str:
    if level is None:
        return "na"
    v = str(level).strip().lower()
    if v in {"very_high", "vhigh"}:
        return "very_high"
    if v in {"high"}:
        return "high"
    if v in {"medium", "mid"}:
        return "medium"
    if v in {"low"}:
        return "low"
    return v


def main() -> int:
    pred_path = Path(os.getenv("PRED_LOG", "api_gateway/data/prediction_events.jsonl"))
    res_path = Path(os.getenv("RESULTS", "api_gateway/data/match_results.jsonl"))
    backtest_out = Path(os.getenv("BACKTEST_OUT", "api_gateway/data/backtest_events.jsonl"))
    buckets_out = Path(os.getenv("BUCKETS_OUT", "api_gateway/data/similarity_buckets.json"))

    min_samples = int(os.getenv("MIN_SAMPLES", "50"))
    prior_a = float(os.getenv("PRIOR_ALPHA", "3"))
    prior_b = float(os.getenv("PRIOR_BETA", "3"))

    results = load_results(res_path)
    if not results:
        print("No results found. Provide api_gateway/data/match_results.jsonl/.json")
        return 2

    backtest_out.parent.mkdir(parents=True, exist_ok=True)
    joined = 0

    # 1) Join into backtest_events.jsonl
    with backtest_out.open("w", encoding="utf-8") as f:
        for p in iter_jsonl(pred_path):
            mid = str(p.get("match_id") or "").strip()
            if not mid or mid not in results:
                continue

            r = results[mid]
            actual = norm_outcome(r.get("outcome") or r.get("result")) or outcome_from_goals(r)
            if actual is None:
                continue

            tier = str(p.get("tier") or "").upper() if p.get("tier") else None
            chaos = p.get("chaos_index")
            frag = p.get("fragility_level")

            probs = p.get("probs") if isinstance(p.get("probs"), dict) else {}
            pick = norm_outcome(p.get("pick"))
            if pick is None:
                p1 = float(probs.get("home_win", 0.0) or 0.0)
                px = float(probs.get("draw", 0.0) or 0.0)
                p2 = float(probs.get("away_win", 0.0) or 0.0)
                pick = "home_win" if (p1 >= px and p1 >= p2) else "draw" if (px >= p1 and px >= p2) else "away_win"

            hit = bool(pick == actual)
            rec = {
                "championship": p.get("championship"),
                "tier": tier,
                "chaos_index": chaos,
                "fragility_level": frag,
                "hit": hit,
                "match_id": mid,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            joined += 1

    # 2) Build buckets with Beta(a,b) smoothing
    agg: Dict[str, Dict[str, float]] = {}
    for r in iter_jsonl(backtest_out):
        champ = str(r.get("championship") or "").strip()
        tier = str(r.get("tier") or "").strip()
        if not champ or not tier:
            continue
        k = f"{champ}|{tier}|{bucketize_chaos(r.get('chaos_index'))}|{norm_fragility(r.get('fragility_level'))}"
        row = agg.setdefault(k, {"hits": 0.0, "n": 0.0})
        row["hits"] += 1.0 if bool(r.get("hit")) else 0.0
        row["n"] += 1.0

    out: Dict[str, Dict[str, Any]] = {}
    for k, row in agg.items():
        n = int(row["n"])
        if n < min_samples:
            continue
        hits = row["hits"]
        acc = (hits + prior_a) / (row["n"] + prior_a + prior_b)
        out[k] = {"accuracy": round(acc, 6), "n": n, "smoothing": {"alpha": prior_a, "beta": prior_b}}

    buckets_out.parent.mkdir(parents=True, exist_ok=True)
    buckets_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Joined={joined}  Buckets={len(out)}  min_samples={min_samples}  prior=Beta({prior_a},{prior_b})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
