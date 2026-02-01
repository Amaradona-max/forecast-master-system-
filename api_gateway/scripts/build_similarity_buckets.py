#!/usr/bin/env python3
"""Build similarity_buckets.json for 'match simili' context reliability.

This script aggregates historical backtest records into buckets:
    championship | tier | chaos_bucket | fragility_level

and computes bucket accuracy (hit-rate) and sample size.

Input is a JSONL (one record per line) or JSON array file.
You can generate it from your existing evaluation pipeline or logs.

Expected minimal fields per record:
- championship: str
- tier: str  (S/A/B/C)
- chaos_index: float (0..100)   OR chaos: float
- fragility_level: str (low/medium/high/very_high)
- hit: bool OR correct: bool OR y_true/y_pred to derive hit

Optional:
- date, match_id, etc. are ignored.

Usage:
    python api_gateway/scripts/build_similarity_buckets.py \
        --input api_gateway/data/backtest_events.jsonl \
        --output api_gateway/data/similarity_buckets.json \
        --min-samples 50

Notes:
- Buckets with samples < min-samples are skipped.
- You can change bucketing thresholds in code.

"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def bucketize_chaos(x: float | None) -> str:
    if x is None:
        return "na"
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


def norm_fragility(level: str | None) -> str:
    if not level:
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


def iter_records(path: Path) -> Iterable[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []
    # JSONL
    if "\n" in text and text.lstrip().startswith("{") and not text.lstrip().startswith("["):
        out = []
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
        return out

    # JSON array or object
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            # allow {"records":[...]}
            recs = obj.get("records")
            if isinstance(recs, list):
                return [x for x in recs if isinstance(x, dict)]
            return [obj]
    except Exception:
        pass
    return []


def derive_hit(r: dict[str, Any]) -> bool | None:
    for k in ("hit", "correct", "is_correct"):
        if k in r:
            v = r.get(k)
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(int(v))
    # allow y_true/y_pred equality
    if "y_true" in r and "y_pred" in r:
        return r.get("y_true") == r.get("y_pred")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="JSONL or JSON file with match-level backtest records")
    ap.add_argument("--output", required=True, help="Where to write similarity_buckets.json")
    ap.add_argument("--min-samples", type=int, default=50, help="Skip buckets with fewer samples")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    min_samples = max(1, int(args.min_samples))

    records = list(iter_records(in_path))
    if not records:
        print("No records found. Check input format/path.")
        out_path.write_text("{}", encoding="utf-8")
        return 0

    # bucket -> [hits, n]
    agg: dict[str, dict[str, float]] = {}
    skipped = 0

    for r in records:
        champ = str(r.get("championship") or r.get("league") or "").strip()
        tier = str(r.get("tier") or r.get("confidence_tier") or "").strip()
        chaos = r.get("chaos_index", r.get("chaos"))
        frag = r.get("fragility_level", r.get("fragility"))

        hit = derive_hit(r)
        if not champ or not tier or hit is None:
            skipped += 1
            continue

        k = f"{champ}|{tier}|{bucketize_chaos(float(chaos) if chaos is not None else None)}|{norm_fragility(str(frag) if frag is not None else None)}"
        row = agg.setdefault(k, {"hits": 0.0, "n": 0.0})
        row["hits"] += 1.0 if hit else 0.0
        row["n"] += 1.0

    out: dict[str, dict[str, Any]] = {}
    for k, row in agg.items():
        n = int(row["n"])
        if n < min_samples:
            continue
        acc = clamp01(row["hits"] / max(1.0, row["n"]))
        out[k] = {"accuracy": round(acc, 6), "n": n}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Buckets written: {len(out)} (min_samples={min_samples})")
    if skipped:
        print(f"Skipped records (missing champ/tier/hit): {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
