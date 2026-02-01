from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OUTCOME_KEYS = ("home_win", "draw", "away_win")


@dataclass(frozen=True)
class GateThresholds:
    min_best_prob: float = 0.55
    min_conf: float = 0.55
    min_gap: float = 0.03

    top_best_prob: float = 0.70
    top_conf: float = 0.70
    top_gap: float = 0.08


def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    if v != v:
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _label_for_outcome(key: str) -> str:
    if key == "home_win":
        return "1"
    if key == "draw":
        return "X"
    if key == "away_win":
        return "2"
    return key


def load_tuned_thresholds(path: str) -> dict[str, dict[str, float]] | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        th = data.get("thresholds")
        return th if isinstance(th, dict) else None
    except Exception:
        return None


def select_thresholds(championship: str, cfg: dict[str, Any] | None) -> GateThresholds:
    if not isinstance(cfg, dict):
        return GateThresholds()

    maybe = cfg.get("thresholds")
    if isinstance(maybe, dict):
        cfg = maybe

    base = dict(cfg.get("default") or {}) if isinstance(cfg.get("default"), dict) else {}

    league = dict(cfg.get(str(championship)) or {}) if isinstance(cfg.get(str(championship)), dict) else {}

    def g(key: str, default: float) -> float:
        raw = league.get(key, base.get(key, default))
        try:
            return float(raw)
        except Exception:
            return float(default)

    return GateThresholds(
        min_best_prob=g("min_best_prob", 0.55),
        min_conf=g("min_conf", 0.55),
        min_gap=g("min_gap", 0.03),
        top_best_prob=g("top_best_prob", 0.70),
        top_conf=g("top_conf", 0.70),
        top_gap=g("top_gap", 0.08),
    )


def adjust_thresholds_for_chaos(th: GateThresholds, chaos_index: float) -> tuple[GateThresholds, dict[str, Any] | None]:
    try:
        c = float(chaos_index)
    except Exception:
        return th, None

    delta_prob = 0.0
    delta_conf = 0.0
    delta_gap = 0.0

    if c >= 85:
        delta_prob, delta_conf, delta_gap = 0.03, 0.03, 0.008
    elif c >= 70:
        delta_prob, delta_conf, delta_gap = 0.02, 0.02, 0.005
    elif c >= 55:
        delta_prob, delta_conf, delta_gap = 0.01, 0.01, 0.003
    else:
        return th, None

    out = GateThresholds(
        min_best_prob=min(0.70, th.min_best_prob + delta_prob),
        min_conf=min(0.75, th.min_conf + delta_conf),
        min_gap=min(0.08, th.min_gap + delta_gap),
        top_best_prob=min(0.85, th.top_best_prob + 0.5 * delta_prob),
        top_conf=min(0.85, th.top_conf + 0.5 * delta_conf),
        top_gap=min(0.15, th.top_gap + 0.5 * delta_gap),
    )

    meta = {"chaos_index": c, "delta": {"prob": delta_prob, "conf": delta_conf, "gap": delta_gap}}
    return out, meta


def _gap_norm(gap: float) -> float:
    try:
        g = float(gap)
    except Exception:
        return 0.0
    if g <= 0:
        return 0.0
    return _clamp01(g / 0.20)


def _extract_chaos_index(chaos: dict[str, Any] | None) -> float | None:
    if not isinstance(chaos, dict):
        return None
    try:
        v = float(chaos.get("index"))
    except Exception:
        return None
    return v if v == v else None


def _extract_fragility_level(fragility: dict[str, Any] | None) -> str | None:
    if not isinstance(fragility, dict):
        return None
    lvl = fragility.get("level")
    if isinstance(lvl, str) and lvl:
        return lvl
    return None


def _build_warnings(*, chaos: dict[str, Any] | None, fragility: dict[str, Any] | None, best_prob: float, conf: float, gap: float) -> list[str]:
    warnings: list[str] = []
    c = _extract_chaos_index(chaos)
    if isinstance(c, (int, float)):
        if c >= 85:
            warnings.append("Caos estremo: altissima varianza, stake minimo")
        elif c >= 70:
            warnings.append("Caos alto: possibile upset, prudenza")
        elif c >= 55:
            warnings.append("Caos medio: match più instabile del normale")

        try:
            if bool(chaos.get("upset_watch")):
                warnings.append("Upset watch: favorita non solidissima")
        except Exception:
            pass

    lvl = _extract_fragility_level(fragility)
    if lvl == "high":
        warnings.append("Match fragile: molto equilibrato (alto rischio swing)")
    elif lvl == "medium":
        warnings.append("Fragilità media: rischio swing moderato")

    if conf >= 0.72 and gap <= 0.035:
        warnings.append("Attenzione: confidence alta ma gap basso (rischio overconfidence)")

    if best_prob >= 0.60 and conf < 0.55:
        warnings.append("Favorita probabile ma affidabilità bassa (segnali incoerenti)")

    out: list[str] = []
    seen: set[str] = set()
    for w in warnings:
        if w not in seen:
            out.append(w)
            seen.add(w)
    return out


def _tier_from_grade(
    *,
    grade: str,
    best_prob: float,
    conf: float,
    gap: float,
    chaos: dict[str, Any] | None,
    fragility: dict[str, Any] | None,
    thresholds: GateThresholds,
) -> str:
    g = str(grade or "").upper()

    c = _extract_chaos_index(chaos)
    frag_lvl = _extract_fragility_level(fragility)

    passes_top = bool(best_prob >= thresholds.top_best_prob and conf >= thresholds.top_conf and gap >= thresholds.top_gap)

    if passes_top:
        stable = True
        if isinstance(c, (int, float)) and c >= 55:
            stable = False
        if frag_lvl in ("high",):
            stable = False
        if stable:
            return "S"
        return "A"

    if g == "A":
        return "A"
    if g == "B":
        return "B"
    return "C"


def evaluate_decision(
    *,
    championship: str,
    probs: dict[str, float],
    confidence: float | None,
    thresholds: GateThresholds,
    chaos: dict[str, Any] | None = None,
    fragility: dict[str, Any] | None = None,
    drift_level: str | None = None,
) -> dict[str, Any]:
    p = {k: _clamp01(float(probs.get(k, 0.0) or 0.0)) for k in OUTCOME_KEYS}
    conf = _clamp01(float(confidence or 0.0))

    items = sorted(p.items(), key=lambda kv: kv[1], reverse=True)
    best_k, best_p = items[0]
    second_p = items[1][1] if len(items) > 1 else 0.0
    gap = max(0.0, best_p - second_p)

    reasons: list[str] = []
    no_bet = False

    if best_p < thresholds.min_best_prob:
        no_bet = True
        reasons.append("Probabilità migliore troppo bassa")
    if conf < thresholds.min_conf:
        no_bet = True
        reasons.append("Affidabilità (confidence) bassa")
    if gap < thresholds.min_gap:
        no_bet = True
        reasons.append("Match troppo equilibrato (gap basso)")

    score = 0.65 * best_p + 0.35 * conf
    confidence_score = _clamp01(0.55 * best_p + 0.25 * conf + 0.20 * _gap_norm(gap))

    if no_bet:
        grade = "D"
    else:
        if best_p >= thresholds.top_best_prob and conf >= thresholds.top_conf and gap >= thresholds.top_gap:
            grade = "A"
        elif score >= 0.72:
            grade = "B"
        elif score >= 0.62:
            grade = "C"
        else:
            grade = "D"
            reasons.append("Segnali non abbastanza forti")

    if no_bet or grade == "D":
        risk = {"label": "Alto", "tone": "red"}
    elif grade == "A":
        risk = {"label": "Basso", "tone": "green"}
    else:
        risk = {"label": "Medio", "tone": "yellow"}

    tier = _tier_from_grade(
        grade=grade,
        best_prob=best_p,
        conf=conf,
        gap=gap,
        chaos=chaos,
        fragility=fragility,
        thresholds=thresholds,
    )
    warnings = _build_warnings(chaos=chaos, fragility=fragility, best_prob=best_p, conf=conf, gap=gap)
    cap = None
    if isinstance(drift_level, str) and drift_level.strip():
        dl = drift_level.strip().lower()
        if dl == "high":
            cap = "B"
        elif dl == "warn":
            cap = "A"
    if cap is not None:
        order = {"S": 3, "A": 2, "B": 1, "C": 0}
        if order.get(tier, 0) > order.get(cap, 0):
            tier = cap
            reasons.append("Drift elevato: confidenza ridotta in automatico")
            warnings.append("Drift: ridotta confidenza")

    return {
        "no_bet": bool(no_bet or grade == "D"),
        "recommended": {
            "outcome_key": str(best_k),
            "label": _label_for_outcome(str(best_k)),
            "prob": float(best_p),
        },
        "runner_up": {
            "outcome_key": str(items[1][0]) if len(items) > 1 else None,
            "label": _label_for_outcome(str(items[1][0])) if len(items) > 1 else None,
            "prob": float(second_p),
        },
        "quality": {"grade": str(grade), "score": float(score)},
        "risk": risk,
        "metrics": {"best_prob": float(best_p), "conf": float(conf), "gap": float(gap)},
        "confidence_tier": str(tier),
        "confidence_score": float(confidence_score),
        "warnings": warnings,
        "thresholds": {
            "min_best_prob": float(thresholds.min_best_prob),
            "min_conf": float(thresholds.min_conf),
            "min_gap": float(thresholds.min_gap),
            "top_best_prob": float(thresholds.top_best_prob),
            "top_conf": float(thresholds.top_conf),
            "top_gap": float(thresholds.top_gap),
        },
        "reasons": reasons,
    }
