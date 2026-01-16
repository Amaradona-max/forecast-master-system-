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

