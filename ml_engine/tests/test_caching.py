import math

from ml_engine import calibration_1x2, logit_1x2_runtime


def test_joblib_loaded_once(monkeypatch) -> None:
    logit_1x2_runtime.load_model.cache_clear()
    calibration_1x2.load_calibrator.cache_clear()

    load_count = {"model": 0, "calib": 0}

    def fake_joblib_load_model(*args, **kwargs):
        load_count["model"] += 1
        return {"pipeline": object(), "feature_cols": ["x"]}

    def fake_joblib_load_calib(*args, **kwargs):
        load_count["calib"] += 1
        return {"params": {}}

    monkeypatch.setattr(logit_1x2_runtime, "_joblib_load", fake_joblib_load_model, raising=True)
    monkeypatch.setattr(calibration_1x2, "_joblib_load", fake_joblib_load_calib, raising=True)

    monkeypatch.setattr(logit_1x2_runtime.os.path, "exists", lambda *_: True, raising=True)
    monkeypatch.setattr(calibration_1x2.os.path, "exists", lambda *_: True, raising=True)

    logit_1x2_runtime.load_model("serie_a")
    logit_1x2_runtime.load_model("serie_a")
    assert load_count["model"] == 1

    calibration_1x2.load_calibrator("serie_a")
    calibration_1x2.load_calibrator("serie_a")
    assert load_count["calib"] == 1


def test_calibration_dirichlet_applied(monkeypatch) -> None:
    calibration_1x2.load_calibrator.cache_clear()

    payload = {
        "method": "dirichlet",
        "coef": [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 2.0]],
        "intercept": [0.0, 0.0, 0.0],
        "eps": 1e-6,
    }

    monkeypatch.setattr(calibration_1x2, "_joblib_load", lambda *_: payload, raising=True)
    monkeypatch.setattr(calibration_1x2.os.path, "exists", lambda *_: True, raising=True)

    probs = {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}
    out, applied = calibration_1x2.calibrate_1x2(championship="serie_a", probs=probs)
    assert applied is True
    assert set(out.keys()) == {"home_win", "draw", "away_win"}
    s = float(out["home_win"]) + float(out["draw"]) + float(out["away_win"])
    assert abs(1.0 - s) < 1e-9
    assert all(0.0 <= float(out[k]) <= 1.0 and math.isfinite(float(out[k])) for k in out)
    assert out != probs


def test_calibration_platt_default_method(monkeypatch) -> None:
    calibration_1x2.load_calibrator.cache_clear()

    payload = {"params": {"H": {"coef": 2.0, "intercept": 0.0}, "D": {"coef": 2.0, "intercept": 0.0}, "A": {"coef": 2.0, "intercept": 0.0}}}

    monkeypatch.setattr(calibration_1x2, "_joblib_load", lambda *_: payload, raising=True)
    monkeypatch.setattr(calibration_1x2.os.path, "exists", lambda *_: True, raising=True)

    probs = {"home_win": 0.45, "draw": 0.35, "away_win": 0.2}
    out, applied = calibration_1x2.calibrate_1x2(championship="serie_a", probs=probs)
    assert applied is True
    s = float(out["home_win"]) + float(out["draw"]) + float(out["away_win"])
    assert abs(1.0 - s) < 1e-9
