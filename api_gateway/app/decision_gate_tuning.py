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


def _trend_factor(trend_row: dict[str, Any] | None) -> float:
    """
    Ritorna un fattore in [-1, +1]:
    +1 => peggiora (più prudenza)
    -1 => migliora (meno prudenza)
    0  => stabile/ignoto

    Regole semplici su delta:
    - accuracy scende >= 2%  OR ece sale >= 0.01 OR logloss sale >= 0.02 => peggiora
    - accuracy sale   >= 2%  AND (ece scende <= -0.01 OR logloss scende <= -0.02) => migliora
    """
    if not isinstance(trend_row, dict):
        return 0.0
    d = trend_row.get("delta")
    if not isinstance(d, dict):
        acc7 = _as_float(trend_row.get("acc7"), None)
        acc30 = _as_float(trend_row.get("acc30"), None)
        ece7 = _as_float(trend_row.get("ece7"), None)
        ece30 = _as_float(trend_row.get("ece30"), None)
        ll7 = _as_float(trend_row.get("logloss7"), None)
        ll30 = _as_float(trend_row.get("logloss30"), None)
        w7 = trend_row.get("window7") if isinstance(trend_row.get("window7"), dict) else {}
        w30 = trend_row.get("window30") if isinstance(trend_row.get("window30"), dict) else {}
        if ll7 is None:
            ll7 = _as_float(w7.get("logloss"), None)
        if ll30 is None:
            ll30 = _as_float(w30.get("logloss"), None)
        if acc7 is None:
            acc7 = _as_float(w7.get("accuracy"), None)
        if acc30 is None:
            acc30 = _as_float(w30.get("accuracy"), None)
        if ece7 is None:
            ece7 = _as_float(w7.get("ece"), None)
        if ece30 is None:
            ece30 = _as_float(w30.get("ece"), None)

        da0 = _as_float(trend_row.get("delta_accuracy"), None)
        de0 = _as_float(trend_row.get("delta_ece"), None)
        dl0 = _as_float(trend_row.get("delta_logloss"), None)

        da = da0 if da0 is not None else (acc7 - acc30 if acc7 is not None and acc30 is not None else 0.0)
        de = de0 if de0 is not None else (ece7 - ece30 if ece7 is not None and ece30 is not None else 0.0)
        dl = dl0 if dl0 is not None else (ll7 - ll30 if ll7 is not None and ll30 is not None else 0.0)
    else:
        try:
            da = float(d.get("accuracy") or 0.0)
            de = float(d.get("ece") or 0.0)
            dl = float(d.get("logloss") or 0.0)
        except Exception:
            return 0.0

    improved = float(da) >= 0.02 and (float(de) <= -0.01 or float(dl) <= -0.02)
    worsened = float(da) <= -0.02 or float(de) >= 0.01 or float(dl) >= 0.02
    if improved:
        return -1.0
    if worsened:
        return +1.0
    return 0.0



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
    trend_weight: float = 0.35
    trend_extra_prob: float = 0.012
    trend_extra_conf: float = 0.012
    trend_extra_gap: float = 0.004


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


def tune_thresholds_for_league(
    *, base: dict[str, float], metrics_row: dict[str, Any] | None, trend_row: dict[str, Any] | None, params: TuneParams
) -> dict[str, float]:
    metrics_row = metrics_row or {}
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
    scores: list[float] = []
    if n >= int(params.min_samples):
        ece = _as_float(metrics_row.get("ece"), None)
        if ece is None:
            ece = _as_float(metrics_row.get("expected_calibration_error"), None)
        logloss = _as_float(metrics_row.get("logloss"), None)
        if logloss is None:
            logloss = _as_float(metrics_row.get("log_loss"), None)
        if logloss is None:
            logloss = _as_float(metrics_row.get("logLoss"), None)

        if ece is not None:
            scores.append(_normalize_good_bad(float(ece), good=float(params.ece_good), bad=float(params.ece_bad)))
        if logloss is not None:
            scores.append(_normalize_good_bad(float(logloss), good=float(params.logloss_good), bad=float(params.logloss_bad)))

    shift_abs = 0.0
    if scores:
        reliability = sum(scores) / float(len(scores))
        shift_abs = _clamp((0.5 - reliability) * 2.0, -1.0, 1.0)

    tf = _trend_factor(trend_row)
    shift = _clamp(float(shift_abs) + float(params.trend_weight) * float(tf), -1.0, 1.0)
    d_prob = float(params.max_delta_prob) * float(shift) + float(params.trend_extra_prob) * float(tf)
    d_conf = float(params.max_delta_conf) * float(shift) + float(params.trend_extra_conf) * float(tf)
    d_gap = float(params.max_delta_gap) * float(shift) + float(params.trend_extra_gap) * float(tf)
    if float(d_prob) == 0.0 and float(d_conf) == 0.0 and float(d_gap) == 0.0:
        return out

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
    backtest_trends_path: str | None = None,
    base_thresholds: dict[str, dict[str, float]],
    out_path: str,
    params: TuneParams | None = None,
) -> dict[str, Any] | None:
    return rebuild_decision_gate_tuned(
        backtest_metrics_path=backtest_metrics_path,
        backtest_trends_path=backtest_trends_path,
        base_thresholds=base_thresholds,
        out_path=out_path,
        params=params,
    )


def rebuild_decision_gate_tuned(
    *,
    backtest_metrics_path: str,
    backtest_trends_path: str | None,
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

    trends = load_json(str(backtest_trends_path)) if backtest_trends_path else None
    trends_champs = trends.get("championships") if isinstance(trends, dict) else None
    if not isinstance(trends_champs, dict):
        trends_champs = {}

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

    keys = set()
    for k in champs.keys():
        if isinstance(k, str):
            keys.add(str(k))
    for k in trends_champs.keys():
        if isinstance(k, str):
            keys.add(str(k))

    for champ in sorted(keys):
        row = champs.get(champ)
        mrow = row if isinstance(row, dict) else {}
        trow0 = trends_champs.get(champ)
        trow = trow0 if isinstance(trow0, dict) else None

        ov = base_thresholds.get(str(champ))
        ov2 = ov if isinstance(ov, dict) else {}
        base = dict(base_default)
        base.update(ov2)
        base_tuned = tune_thresholds_for_league(base=base, metrics_row=mrow, trend_row=None, params=params)

        tf = _trend_factor(trends_champs.get(str(champ)) if isinstance(trends_champs, dict) else None)
        if tf != 0.0:
            base_tuned["min_best_prob"] = float(
                _clamp(base_tuned.get("min_best_prob", 0.55) + tf * params.trend_extra_prob, 0.50, 0.70)
            )
            base_tuned["min_conf"] = float(_clamp(base_tuned.get("min_conf", 0.55) + tf * params.trend_extra_conf, 0.50, 0.75))
            base_tuned["min_gap"] = float(_clamp(base_tuned.get("min_gap", 0.03) + tf * params.trend_extra_gap, 0.01, 0.08))
            base_tuned["_trend"] = {"factor": float(tf)}

        tuned[str(champ)] = base_tuned

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
            "model": "decision_gate_tuning_v2_trend_aware",
            "source_metrics": str(backtest_metrics_path),
            "source_trends": str(backtest_trends_path) if backtest_trends_path else None,
            "metrics_present": bool(champs),
            "trends_present": bool(trends_champs),
            "params": {
                "ece_good": params.ece_good,
                "ece_bad": params.ece_bad,
                "logloss_good": params.logloss_good,
                "logloss_bad": params.logloss_bad,
                "max_delta_prob": params.max_delta_prob,
                "max_delta_conf": params.max_delta_conf,
                "max_delta_gap": params.max_delta_gap,
                "min_samples": params.min_samples,
                "trend_weight": params.trend_weight,
                "trend_extra_prob": params.trend_extra_prob,
                "trend_extra_conf": params.trend_extra_conf,
                "trend_extra_gap": params.trend_extra_gap,
            },
        },
        "thresholds": {k: v for k, v in sorted(tuned.items(), key=lambda kv: kv[0])},
    }

    write_json(out_path, payload)
    return payload
