import math

import pytest

from ml_engine.ensemble_predictor.service import EnsemblePredictorService


def _assert_probs_ok(probs: dict) -> None:
    for k in ("home_win", "draw", "away_win"):
        assert k in probs
        v = probs[k]
        assert isinstance(v, (int, float))
        assert math.isfinite(float(v))
        assert 0.0 <= float(v) <= 1.0
    s = float(probs["home_win"]) + float(probs["draw"]) + float(probs["away_win"])
    assert abs(1.0 - s) < 1e-6


@pytest.mark.parametrize("championship,home,away", [("serie_a", "Inter", "Milan"), ("premier_league", "Arsenal", "Chelsea"), ("la_liga", "Real Madrid", "Barcelona"), ("bundesliga", "Bayern Munich", "Dortmund")])
def test_invariants_basic(championship: str, home: str, away: str) -> None:
    svc = EnsemblePredictorService()
    out = svc.predict(championship=championship, home_team=home, away_team=away, status="PREMATCH", context={"matchday": 12})
    _assert_probs_ok(out["probabilities"])

