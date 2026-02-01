from __future__ import annotations

import math
from typing import Dict

LABELS = ("home_win", "draw", "away_win")


def _safe_probs(probs: Dict[str, float]) -> Dict[str, float]:
    p = {k: float(probs.get(k, 0.0) or 0.0) for k in LABELS}
    s = sum(max(0.0, v) for v in p.values())
    if s <= 0:
        return {k: 1.0 / 3.0 for k in LABELS}
    out = {k: max(0.0, v) / s for k, v in p.items()}
    eps = 1e-12
    out = {k: max(eps, v) for k, v in out.items()}
    s2 = sum(out.values())
    return {k: v / s2 for k, v in out.items()}


def _entropy_norm(p: Dict[str, float]) -> float:
    h = 0.0
    for v in p.values():
        h += -float(v) * math.log(float(v))
    h_max = math.log(3.0)
    return float(h / h_max) if h_max > 0 else 0.0


def fragility_from_probs(probs: Dict[str, float]) -> Dict:
    p = _safe_probs(probs)

    ranked = sorted(p.items(), key=lambda kv: kv[1], reverse=True)
    top_k, top_p = ranked[0]
    second_k, second_p = ranked[1]

    margin = float(top_p - second_p)
    ent = float(_entropy_norm(p))

    flip_distance = float(max(0.0, margin / 2.0))

    score = 0.65 * (1.0 - margin) + 0.35 * ent
    score = float(min(1.0, max(0.0, score)))

    if score >= 0.67:
        level = "high"
    elif score >= 0.40:
        level = "medium"
    else:
        level = "low"

    return {
        "score": score,
        "level": level,
        "margin": margin,
        "entropy": ent,
        "top": top_k,
        "runner_up": second_k,
        "flip_distance": flip_distance,
    }
