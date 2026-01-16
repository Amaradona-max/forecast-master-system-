import math
import sys

from ml_engine.ensemble_predictor.service import EnsemblePredictorService


def die(msg: str) -> None:
    print(f"[INVARIANTS] ERROR: {msg}")
    raise SystemExit(2)


def assert_probs_ok(p: dict) -> None:
    for k in ("home_win", "draw", "away_win"):
        if k not in p:
            die(f"Missing key {k}")
        v = p[k]
        if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            die(f"{k} invalid: {v}")
        if not (0.0 <= float(v) <= 1.0):
            die(f"{k} out of [0,1]: {v}")
    s = float(p["home_win"]) + float(p["draw"]) + float(p["away_win"])
    if abs(1.0 - s) > 1e-6:
        die(f"sum != 1: {s}")


def main() -> None:
    svc = EnsemblePredictorService()

    samples = [
        {"championship": "serie_a", "home_team": "Inter", "away_team": "Milan"},
        {"championship": "premier_league", "home_team": "Arsenal", "away_team": "Chelsea"},
        {"championship": "la_liga", "home_team": "Real Madrid", "away_team": "Barcelona"},
        {"championship": "bundesliga", "home_team": "Bayern Munich", "away_team": "Dortmund"},
    ]

    for ctx in samples:
        out = svc.predict(championship=ctx["championship"], home_team=ctx["home_team"], away_team=ctx["away_team"], status="PREMATCH", context={"matchday": 12})
        assert_probs_ok(out.get("probabilities", {}))
        conf = out.get("confidence", {})
        score = conf.get("score") if isinstance(conf, dict) else None
        if score is not None and not (0.0 <= float(score) <= 1.0):
            die(f"confidence out of [0,1]: {score}")

    print("[INVARIANTS] OK")


if __name__ == "__main__":
    main()

