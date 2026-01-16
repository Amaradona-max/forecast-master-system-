from __future__ import annotations

import os

from api_gateway.app.services import PredictionService


def test_prediction_service_read_through_cache(tmp_path, monkeypatch) -> None:
    os.environ["FORECAST_CACHE_DB"] = str(tmp_path / "cache.sqlite")

    svc = PredictionService()
    ctx = {"matchday": 1, "calibration": {"alpha": 0.0}}

    out1 = svc.predict_match(
        championship="serie_a",
        match_id="serie_a_test_001",
        home_team="Inter",
        away_team="Milan",
        status="PREMATCH",
        kickoff_unix=None,
        context=ctx,
    )
    assert isinstance(out1.explain, dict)
    c1 = out1.explain.get("cache")
    assert isinstance(c1, dict)
    assert c1.get("hit") is False

    out2 = svc.predict_match(
        championship="serie_a",
        match_id="serie_a_test_001",
        home_team="Inter",
        away_team="Milan",
        status="PREMATCH",
        kickoff_unix=None,
        context=ctx,
    )
    assert isinstance(out2.explain, dict)
    c2 = out2.explain.get("cache")
    assert isinstance(c2, dict)
    assert c2.get("hit") is True

