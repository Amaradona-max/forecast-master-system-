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


@lru_cache(maxsize=32)
def _load_calibrator_cached(championship: str, artifact_dir: str) -> dict[str, Any] | None:
    path = os.path.join(artifact_dir, f"calibrator_1x2_{championship}.joblib")
    if not os.path.exists(path):
        return None
    try:
        payload = _joblib_load(path)
    except CircuitOpenError:
        return None
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_calibrator(championship: str) -> dict[str, Any] | None:
    return _load_calibrator_cached(championship, _default_artifact_dir())


load_calibrator.cache_clear = _load_calibrator_cached.cache_clear  # type: ignore[attr-defined]


def calibrate_1x2(*, championship: str, probs: dict[str, float]) -> tuple[dict[str, float], bool]:
    calib = load_calibrator(championship)
    if calib is None:
        return probs, False

    method = str(calib.get("method") or "platt_ovr").strip().lower()
    params = calib.get("params")
    if not isinstance(params, dict):
        params = {}
    if method != "dirichlet" and not isinstance(params, dict):
        return probs, False

    p_h = float(probs.get("home_win", 0.0) or 0.0)
    p_d = float(probs.get("draw", 0.0) or 0.0)
    p_a = float(probs.get("away_win", 0.0) or 0.0)
    s = max(p_h, 0.0) + max(p_d, 0.0) + max(p_a, 0.0)
    if s <= 0:
        p_h, p_d, p_a = 1 / 3, 1 / 3, 1 / 3
    else:
        p_h, p_d, p_a = max(p_h, 0.0) / s, max(p_d, 0.0) / s, max(p_a, 0.0) / s

    if method == "dirichlet":
        coef0 = params.get("coef") if "coef" in params else calib.get("coef")
        intercept0 = params.get("intercept") if "intercept" in params else calib.get("intercept")
        if not isinstance(coef0, list) or not isinstance(intercept0, list):
            return probs, False

        try:
            coef = [[float(x) for x in row] for row in coef0]
            intercept = [float(x) for x in intercept0]
        except Exception:
            return probs, False

        if len(coef) != 3 or any(len(row) != 3 for row in coef) or len(intercept) != 3:
            return probs, False

        eps0 = params.get("eps") if "eps" in params else calib.get("eps")
        eps = float(eps0) if isinstance(eps0, (int, float)) and float(eps0) > 0 else 1e-6

        def clamp(p: float) -> float:
            if p < eps:
                return eps
            if p > 1.0:
                return 1.0
            return p

        x0 = [math.log(clamp(p_h)), math.log(clamp(p_d)), math.log(clamp(p_a))]
        z0 = [0.0, 0.0, 0.0]
        for i in range(3):
            srow = 0.0
            row = coef[i]
            for j in range(3):
                srow += row[j] * x0[j]
            z0[i] = srow + intercept[i]

        m = max(z0)
        e0 = [math.exp(z0[0] - m), math.exp(z0[1] - m), math.exp(z0[2] - m)]
        s2 = e0[0] + e0[1] + e0[2]
        if s2 <= 0:
            return {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}, True
        return {"home_win": e0[0] / s2, "draw": e0[1] / s2, "away_win": e0[2] / s2}, True

    def logit(p: float) -> float:
        p = 1e-6 if p < 1e-6 else (1.0 - 1e-6 if p > 1.0 - 1e-6 else p)
        return math.log(p / (1.0 - p))

    def sigmoid(x: float) -> float:
        if x < -60:
            return 0.0
        if x > 60:
            x = 60
        return 1.0 / (1.0 + math.exp(-x))

    def apply_one(key: str, p: float) -> float:
        row = params.get(key)
        if not isinstance(row, dict):
            return p
        coef = row.get("coef")
        intercept = row.get("intercept")
        if not isinstance(coef, (int, float)) or not isinstance(intercept, (int, float)):
            return p
        z = float(coef) * logit(p) + float(intercept)
        return sigmoid(z)

    ph2 = apply_one("H", p_h)
    pd2 = apply_one("D", p_d)
    pa2 = apply_one("A", p_a)
    s2 = max(ph2, 0.0) + max(pd2, 0.0) + max(pa2, 0.0)
    if s2 <= 0:
        return {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}, True
    return {"home_win": max(ph2, 0.0) / s2, "draw": max(pd2, 0.0) / s2, "away_win": max(pa2, 0.0) / s2}, True
