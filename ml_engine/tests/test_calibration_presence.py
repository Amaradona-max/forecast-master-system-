import os

import pytest

from ml_engine.ensemble_predictor.service import EnsemblePredictorService


@pytest.mark.parametrize("championship,home,away", [("serie_a", "Inter", "Milan"), ("premier_league", "Arsenal", "Chelsea"), ("la_liga", "Real Madrid", "Barcelona"), ("bundesliga", "Bayern Munich", "Dortmund")])
def test_calibration_flag_matches_artifact_presence(championship: str, home: str, away: str) -> None:
    svc = EnsemblePredictorService()
    out = svc.predict(championship=championship, home_team=home, away_team=away, status="PREMATCH", context={"matchday": 12})

    artifact_dir = os.getenv("ARTIFACT_DIR", "data/models")
    calib_path = os.path.join(artifact_dir, f"calibrator_1x2_{championship}.joblib")
    calib_exists = os.path.exists(calib_path)

    explain = out.get("explain", {})
    comps = explain.get("ensemble_components", {}) if isinstance(explain, dict) else {}
    calibrated_flag = bool(comps.get("calibrated")) if isinstance(comps, dict) else False

    assert calibrated_flag == bool(calib_exists)

