import pytest

from ml_engine.ensemble_predictor.service import EnsemblePredictorService


def _uniformity_distance(p: dict[str, float]) -> float:
    return abs(p["home_win"] - 1 / 3) + abs(p["draw"] - 1 / 3) + abs(p["away_win"] - 1 / 3)


@pytest.mark.parametrize(
    "championship,home,away",
    [
        ("serie_a", "Inter", "Milan"),
        ("premier_league", "Arsenal", "Chelsea"),
        ("la_liga", "Real Madrid", "Barcelona"),
        ("bundesliga", "Bayern Munich", "Dortmund"),
    ],
)
def test_missing_ratings_shrinks_and_lowers_confidence(championship: str, home: str, away: str) -> None:
    svc = EnsemblePredictorService()

    out_full = svc.predict(championship=championship, home_team=home, away_team=away, status="PREMATCH", context={"matchday": 12})
    probs_full = out_full["probabilities"]
    conf_full = float(out_full["confidence"]["score"])

    out_miss1 = svc.predict(championship=championship, home_team=home, away_team="ZZZ Missing Team", status="PREMATCH", context={"matchday": 12})
    probs_miss1 = out_miss1["probabilities"]
    conf_miss1 = float(out_miss1["confidence"]["score"])

    out_miss2 = svc.predict(championship=championship, home_team="YYY Missing Team", away_team="ZZZ Missing Team", status="PREMATCH", context={"matchday": 12})
    probs_miss2 = out_miss2["probabilities"]
    conf_miss2 = float(out_miss2["confidence"]["score"])

    assert _uniformity_distance(probs_miss1) <= _uniformity_distance(probs_full) + 1e-9
    assert _uniformity_distance(probs_miss2) <= _uniformity_distance(probs_miss1) + 1e-9

    assert conf_miss1 <= conf_full + 1e-9
    assert conf_miss2 <= conf_miss1 + 1e-9

