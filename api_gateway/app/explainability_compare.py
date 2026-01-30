import math
from typing import Dict, List


def compare_shap_like(
    *,
    explain_a: Dict,
    explain_b: Dict,
    features_a: Dict[str, float],
    features_b: Dict[str, float],
    coefs: Dict[str, Dict[str, float]],
    target: str,
    top_k: int = 6,
) -> Dict:
    deltas: List[tuple[str, float]] = []

    for fname in features_a.keys():
        ca = float(features_a.get(fname, 0.0)) * float(coefs.get(target, {}).get(fname, 0.0))
        cb = float(features_b.get(fname, 0.0)) * float(coefs.get(target, {}).get(fname, 0.0))
        d = ca - cb
        if not math.isfinite(d) or abs(d) < 1e-6:
            continue
        deltas.append((fname, d))

    total = sum(abs(d) for _, d in deltas)
    if total <= 0:
        total = 1.0

    drivers: List[Dict] = []
    for f, d in deltas:
        drivers.append({"feature": f, "delta": d, "impact_pct": abs(d) / total * 100.0, "winner": "A" if d > 0 else "B"})

    drivers.sort(key=lambda x: x["impact_pct"], reverse=True)

    return {"target": target, "drivers": drivers[: int(top_k)]}
