from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from ml_engine.features.builder import build_features_1x2
from ml_engine.logit_1x2_runtime import load_model
from ml_engine.team_ratings_store import get_team_strength


def compute_shap_like(
    *,
    features: Dict[str, float],
    coefs: Dict[str, Dict[str, float]],
    intercepts: Dict[str, float],
    target: str,
    top_k: int = 5,
) -> Dict:
    contribs: List[Tuple[str, float]] = []
    for fname, fval in features.items():
        coef = coefs.get(target, {}).get(fname)
        if coef is None:
            continue
        c = float(fval) * float(coef)
        if math.isfinite(c):
            contribs.append((fname, c))

    bias = intercepts.get(target, 0.0)
    total = sum(abs(c) for _, c in contribs) + abs(bias)

    def pct(x: float) -> float:
        return abs(x) / total * 100 if total > 0 else 0

    pos = [(f, c, pct(c)) for f, c in contribs if c > 0]
    neg = [(f, c, pct(c)) for f, c in contribs if c < 0]

    pos.sort(key=lambda x: x[2], reverse=True)
    neg.sort(key=lambda x: x[2], reverse=True)

    return {
        "target": target,
        "bias": bias,
        "top_positive": pos[:top_k],
        "top_negative": neg[:top_k],
    }


def _resolve_target_key(target: str, coefs: Dict[str, Dict[str, float]]) -> str | None:
    if target in coefs:
        return target
    mapping = {"home_win": "H", "draw": "D", "away_win": "A"}
    mapped = mapping.get(str(target))
    if mapped and mapped in coefs:
        return mapped
    return None


def compute_feature_contributions(
    *,
    features: Dict[str, float],
    coefs: Dict[str, Dict[str, float]],
    target: str,
) -> Dict[str, float] | None:
    target_key = _resolve_target_key(str(target), coefs)
    if target_key is None:
        return None
    out: Dict[str, float] = {}
    coef_row = coefs.get(target_key, {})
    for fname, fval in features.items():
        coef = coef_row.get(fname)
        if coef is None:
            continue
        c = float(fval) * float(coef)
        if math.isfinite(c):
            out[str(fname)] = float(c)
    return out


def compare_feature_contributions(
    *,
    features_a: Dict[str, float],
    features_b: Dict[str, float],
    coefs: Dict[str, Dict[str, float]],
    target: str,
    top_k: int = 6,
) -> Dict[str, Any] | None:
    contrib_a = compute_feature_contributions(features=features_a, coefs=coefs, target=target)
    contrib_b = compute_feature_contributions(features=features_b, coefs=coefs, target=target)
    if not isinstance(contrib_a, dict) or not isinstance(contrib_b, dict):
        return None

    all_features = set(contrib_a.keys()) | set(contrib_b.keys())
    deltas: Dict[str, float] = {}
    for name in all_features:
        d = float(contrib_a.get(name, 0.0)) - float(contrib_b.get(name, 0.0))
        if math.isfinite(d):
            deltas[str(name)] = float(d)

    total = sum(abs(v) for v in deltas.values())
    if total <= 0:
        return None

    drivers: list[dict[str, Any]] = []
    for name, d in sorted(deltas.items(), key=lambda x: abs(x[1]), reverse=True)[: max(1, int(top_k))]:
        impact = abs(float(d)) / total * 100.0 if total > 0 else 0.0
        winner = "A" if d > 0 else "B" if d < 0 else "TIE"
        drivers.append({"feature": str(name), "delta": round(float(d), 4), "impact_pct": round(float(impact), 1), "winner": winner})

    return {"target": str(target), "drivers": drivers}


def _is_finite(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def _pick_target(probs: dict[str, float]) -> str | None:
    if not isinstance(probs, dict):
        return None
    best = None
    best_v = -1.0
    for k in ("home_win", "draw", "away_win"):
        v = probs.get(k)
        if not isinstance(v, (int, float)):
            continue
        fv = float(v)
        if not math.isfinite(fv):
            continue
        if fv > best_v:
            best_v = fv
            best = k
    return best


def _target_label(target: str) -> str | None:
    if target == "home_win":
        return "H"
    if target == "draw":
        return "D"
    if target == "away_win":
        return "A"
    return None


def _build_row(feature_cols: list[str], features: dict[str, Any]) -> list[float]:
    out: list[float] = []
    for col in feature_cols:
        v = features.get(col)
        if isinstance(v, (int, float)) and _is_finite(v):
            out.append(float(v))
        else:
            out.append(float("nan"))
    return out


def _transform_features(pipe: Any, row: list[float]) -> list[float] | None:
    try:
        import numpy as np  # type: ignore[import-not-found]

        X: Any = np.asarray([row], dtype=float)
    except Exception:
        return None

    steps = getattr(pipe, "steps", None)
    if isinstance(steps, list):
        for name, step in steps:
            if name == "clf":
                break
            if hasattr(step, "transform"):
                try:
                    X = step.transform(X)
                except Exception:
                    return None
    return list(X[0]) if hasattr(X, "__len__") and len(X) > 0 else None


def build_explainability(
    *,
    championship: str,
    home_team: str,
    away_team: str,
    context: dict[str, Any],
    probs: dict[str, float],
    target: str | None = None,
    top_k: int = 3,
) -> dict[str, Any] | None:
    payload = load_model(str(championship))
    if not isinstance(payload, dict):
        return None
    pipe = payload.get("pipeline")
    feature_cols = payload.get("feature_cols")
    if pipe is None or not isinstance(feature_cols, list) or not feature_cols:
        return None
    clf = getattr(pipe, "named_steps", {}).get("clf") if hasattr(pipe, "named_steps") else None
    if clf is None and hasattr(pipe, "coef_"):
        clf = pipe
    if clf is None or not hasattr(clf, "coef_"):
        return None

    classes = getattr(clf, "classes_", None)
    if not isinstance(classes, (list, tuple)):
        classes = payload.get("labels")
    if not isinstance(classes, (list, tuple)):
        return None

    target_key = target or _pick_target(probs)
    if not target_key:
        return None
    label = _target_label(str(target_key))
    if label is None:
        return None

    cls_list = [str(c) for c in list(classes)]
    if label not in cls_list:
        return None
    idx = cls_list.index(label)

    home_lookup = get_team_strength(championship=str(championship), team=str(home_team))
    away_lookup = get_team_strength(championship=str(championship), team=str(away_team))
    home_elo = home_lookup.meta.get("elo") if home_lookup is not None else None
    away_elo = away_lookup.meta.get("elo") if away_lookup is not None else None
    features, _, _ = build_features_1x2(home_elo=home_elo, away_elo=away_elo, context=context)
    row = _build_row([str(c) for c in feature_cols], features)

    transformed = _transform_features(pipe, row)
    if not isinstance(transformed, list):
        return None

    try:
        coef = clf.coef_
    except Exception:
        return None
    if not hasattr(coef, "__len__") or idx >= len(coef):
        return None

    coef_row = coef[idx]
    contributions: list[tuple[str, float]] = []
    for i, col in enumerate(feature_cols):
        if i >= len(coef_row) or i >= len(transformed):
            break
        try:
            v = float(transformed[i])
            c = float(coef_row[i]) * v
        except Exception:
            continue
        if not math.isfinite(c):
            continue
        contributions.append((str(col), float(c)))

    abs_sum = sum(abs(c) for _, c in contributions)
    if abs_sum <= 0:
        return None

    pos = sorted([x for x in contributions if x[1] > 0], key=lambda x: x[1], reverse=True)
    neg = sorted([x for x in contributions if x[1] < 0], key=lambda x: x[1])

    def _pack(items: list[tuple[str, float]]) -> list[list[Any]]:
        out: list[list[Any]] = []
        for name, c in items[: max(1, int(top_k))]:
            w = abs(float(c)) / abs_sum * 100.0 if abs_sum > 0 else 0.0
            out.append([str(name), round(float(c), 4), round(float(w), 1)])
        return out

    return {"target": str(target_key), "top_positive": _pack(pos), "top_negative": _pack(neg)}
