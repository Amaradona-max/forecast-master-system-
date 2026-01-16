from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Any

import joblib

from ml_engine.resilience.circuit_breaker import CircuitOpenError, get_breaker


def _default_artifact_dir() -> str:
    return os.getenv("ARTIFACT_DIR", "data/models")


def _joblib_load(path: str) -> Any:
    return get_breaker("artifacts").call(joblib.load, path)


def _is_finite_number(v: Any) -> bool:
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


@lru_cache(maxsize=32)
def _load_model_cached(championship: str, artifact_dir: str) -> dict[str, Any] | None:
    path = os.path.join(artifact_dir, f"model_1x2_{championship}.joblib")
    if not os.path.exists(path):
        return None
    try:
        payload = _joblib_load(path)
    except CircuitOpenError:
        return None
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if "pipeline" not in payload or "feature_cols" not in payload:
        return None
    return payload


def load_model(championship: str) -> dict[str, Any] | None:
    return _load_model_cached(championship, _default_artifact_dir())


load_model.cache_clear = _load_model_cached.cache_clear  # type: ignore[attr-defined]


def predict_1x2(*, championship: str, features: dict[str, Any]) -> dict[str, float] | None:
    payload = load_model(championship)
    if payload is None:
        return None

    pipe = payload.get("pipeline")
    feature_cols = payload.get("feature_cols")
    if not isinstance(feature_cols, list) or not feature_cols:
        return None

    row: list[float] = []
    cols = [str(c) for c in feature_cols]
    for col in cols:
        v = features.get(col)
        if isinstance(v, (int, float)) and _is_finite_number(v):
            row.append(float(v))
        else:
            row.append(float("nan"))
    try:
        import numpy as np  # type: ignore[import-not-found]

        X: Any = np.asarray([row], dtype=float)
    except Exception:
        X = [row]

    try:
        proba = pipe.predict_proba(X)
    except Exception:
        return None
    if not hasattr(proba, "__len__") or len(proba) != 1:
        return None
    row0 = proba[0]
    if not hasattr(row0, "__len__"):
        return None

    classes = getattr(pipe, "classes_", None)
    if not isinstance(classes, (list, tuple)):
        clf = getattr(pipe, "named_steps", {}).get("clf") if hasattr(pipe, "named_steps") else None
        classes = getattr(clf, "classes_", None)
    if not isinstance(classes, (list, tuple)):
        classes = payload.get("labels")
    if not isinstance(classes, (list, tuple)):
        return None

    out: dict[str, float] = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}
    for i, c in enumerate(list(classes)):
        if i >= len(row0):
            break
        try:
            p = float(row0[i])
        except Exception:
            p = 0.0
        if not _is_finite_number(p):
            p = 0.0
        if str(c) == "H":
            out["home_win"] = p
        elif str(c) == "D":
            out["draw"] = p
        elif str(c) == "A":
            out["away_win"] = p

    s = max(out["home_win"], 0.0) + max(out["draw"], 0.0) + max(out["away_win"], 0.0)
    if s <= 0:
        return {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
    return {"home_win": max(out["home_win"], 0.0) / s, "draw": max(out["draw"], 0.0) / s, "away_win": max(out["away_win"], 0.0) / s}
