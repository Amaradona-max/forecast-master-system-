from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: str) -> Any | None:
    p = Path(str(path or "")).expanduser()
    if not str(p):
        return None
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception:
        return None


def write_json(path: str, payload: dict[str, Any]) -> None:
    p = Path(str(path or "")).expanduser()
    if not str(p):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    if v != v:
        v = 0.0
    return max(float(lo), min(float(hi), float(v)))


def _as_float(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        x = float(v)
    except Exception:
        return default
    if x != x:
        return default
    return float(x)


@dataclass(frozen=True)
class TuneParams:
    ece_good: float = 0.06
    ece_bad: float = 0.12
    logloss_good: float = 0.98
    logloss_bad: float = 1.08
    max_delta_prob: float = 0.03
    max_delta_conf: float = 0.03
    max_delta_gap: float = 0.015
    min_samples: int = 80


def _normalize_good_bad(x: float, *, good: float, bad: float) -> float:
    g = float(good)
    b = float(bad)
    v = float(x)
    if b == g:
        return 1.0 if v <= g else 0.0
    if v <= g:
        return 1.0
    if v >= b:
        return 0.0
    return 1.0 - ((v - g) / (b - g))


def tune_thresholds_for_league(*, base: dict[str, float], metrics_row: dict[str, Any], params: TuneParams) -> dict[str, float]:
    n0 = metrics_row.get("n")
    try:
        n = int(n0)
    except Exception:
        n = 0

    out: dict[str, float] = {}
    for k, v in (base or {}).items():
        if not isinstance(k, str):
            continue
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    if n < int(params.min_samples):
        return out

    ece = _as_float(metrics_row.get("ece"), None)
    if ece is None:
        ece = _as_float(metrics_row.get("expected_calibration_error"), None)
    logloss = _as_float(metrics_row.get("logloss"), None)
    if logloss is None:
        logloss = _as_float(metrics_row.get("log_loss"), None)
    if logloss is None:
        logloss = _as_float(metrics_row.get("logLoss"), None)

    if ece is None and logloss is None:
        return out

    scores: list[float] = []
    if ece is not None:
        scores.append(_normalize_good_bad(float(ece), good=float(params.ece_good), bad=float(params.ece_bad)))
    if logloss is not None:
        scores.append(_normalize_good_bad(float(logloss), good=float(params.logloss_good), bad=float(params.logloss_bad)))

    if not scores:
        return out

    reliability = sum(scores) / float(len(scores))
    shift = _clamp((0.5 - reliability) * 2.0, -1.0, 1.0)

    d_prob = float(params.max_delta_prob) * float(shift)
    d_conf = float(params.max_delta_conf) * float(shift)
    d_gap = float(params.max_delta_gap) * float(shift)

    def f(key: str, delta: float, lo: float, hi: float) -> None:
        raw = out.get(key)
        try:
            base_v = float(raw) if raw is not None else 0.0
        except Exception:
            base_v = 0.0
        out[key] = _clamp(base_v + float(delta), float(lo), float(hi))

    f("min_best_prob", d_prob, 0.45, 0.80)
    f("min_conf", d_conf, 0.45, 0.85)
    f("min_gap", d_gap, 0.0, 0.20)
    f("top_best_prob", d_prob, 0.55, 0.92)
    f("top_conf", d_conf, 0.55, 0.92)
    f("top_gap", d_gap, 0.02, 0.30)

    out["top_best_prob"] = max(float(out.get("top_best_prob", 0.70)), float(out.get("min_best_prob", 0.55)) + 0.05)
    out["top_conf"] = max(float(out.get("top_conf", 0.70)), float(out.get("min_conf", 0.55)) + 0.05)
    out["top_gap"] = max(float(out.get("top_gap", 0.08)), float(out.get("min_gap", 0.03)) + 0.02)

    return out


def rebuild_decision_gate_tuned_to_file(
    *,
    backtest_metrics_path: str,
    base_thresholds: dict[str, dict[str, float]],
    out_path: str,
    params: TuneParams | None = None,
) -> dict[str, Any] | None:
    params = params or TuneParams()
    data = load_json(str(backtest_metrics_path))
    if not isinstance(data, dict):
        data = {}

    champs0 = data.get("championships")
    champs = champs0 if isinstance(champs0, dict) else data.get("leagues")
    if not isinstance(champs, dict):
        champs = {}

    base_default = dict(base_thresholds.get("default") or {}) if isinstance(base_thresholds.get("default"), dict) else {}
    tuned_default: dict[str, float] = {}
    for k, v in base_default.items():
        if not isinstance(k, str):
            continue
        try:
            tuned_default[str(k)] = float(v)
        except Exception:
            continue
    tuned: dict[str, Any] = {"default": tuned_default}

    for champ, row in champs.items():
        if not isinstance(champ, str):
            continue
        if not isinstance(row, dict):
            continue
        ov = base_thresholds.get(str(champ))
        ov2 = ov if isinstance(ov, dict) else {}
        base = dict(base_default)
        base.update(ov2)
        tuned[str(champ)] = tune_thresholds_for_league(base=base, metrics_row=row, params=params)

    for champ, base in base_thresholds.items():
        if not isinstance(champ, str) or champ == "default":
            continue
        if str(champ) in tuned:
            continue
        if not isinstance(base, dict):
            continue
        full = dict(base_default)
        full.update(base)
        tuned_full: dict[str, float] = {}
        for k, v in full.items():
            if not isinstance(k, str):
                continue
            try:
                tuned_full[str(k)] = float(v)
            except Exception:
                continue
        tuned[str(champ)] = tuned_full

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_unix": float(time.time()),
        "meta": {
            "model": "decision_gate_tuning_v1",
            "source_metrics": str(backtest_metrics_path),
            "metrics_present": bool(champs),
            "params": {
                "ece_good": params.ece_good,
                "ece_bad": params.ece_bad,
                "logloss_good": params.logloss_good,
                "logloss_bad": params.logloss_bad,
                "max_delta_prob": params.max_delta_prob,
                "max_delta_conf": params.max_delta_conf,
                "max_delta_gap": params.max_delta_gap,
                "min_samples": params.min_samples,
            },
        },
        "thresholds": {k: v for k, v in sorted(tuned.items(), key=lambda kv: kv[0])},
    }

    write_json(out_path, payload)
    return payload


def rebuild_decision_gate_tuned(
    *,
    backtest_metrics_path: str,
    base_thresholds: dict[str, dict[str, float]],
    out_path: str,
    params: TuneParams | None = None,
) -> dict[str, Any] | None:
    return rebuild_decision_gate_tuned_to_file(
        backtest_metrics_path=backtest_metrics_path,
        base_thresholds=base_thresholds,
        out_path=out_path,
        params=params,
    )
