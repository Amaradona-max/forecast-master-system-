import json
import os
import sys


LEAGUES = ["serie_a", "premier_league", "la_liga", "bundesliga"]


def die(msg: str, code: int = 2) -> None:
    print(f"[ARTIFACT CHECK] ERROR: {msg}")
    raise SystemExit(code)


def warn(msg: str) -> None:
    print(f"[ARTIFACT CHECK] WARNING: {msg}")


def main() -> None:
    artifact_dir = os.getenv("ARTIFACT_DIR", "data/models")
    strict = os.getenv("STRICT_CALIBRATOR", "0") == "1"

    if not os.path.isdir(artifact_dir):
        die(f"Artifact dir not found: {artifact_dir}")

    missing: list[str] = []
    missing_calib: list[str] = []
    for lg in LEAGUES:
        model = os.path.join(artifact_dir, f"model_1x2_{lg}.joblib")
        metrics = os.path.join(artifact_dir, f"metrics_1x2_{lg}.json")
        calib = os.path.join(artifact_dir, f"calibrator_1x2_{lg}.joblib")

        if not os.path.exists(model):
            missing.append(model)
        if not os.path.exists(metrics):
            missing.append(metrics)
        if not os.path.exists(calib):
            missing_calib.append(calib)

        if os.path.exists(metrics):
            try:
                with open(metrics, "r", encoding="utf-8") as f:
                    j = json.load(f)
                for key in ["log_loss", "brier_score", "samples_train", "samples_calibrate"]:
                    if key not in j:
                        warn(f"{metrics} missing key {key}")
            except Exception as e:
                die(f"Failed to parse metrics file {metrics}: {e}")

    if missing:
        die("Missing required artifacts:\n" + "\n".join(missing))

    if missing_calib:
        msg = "Missing calibrators:\n" + "\n".join(missing_calib)
        if strict:
            die(msg)
        warn(msg)

    print("[ARTIFACT CHECK] OK")


if __name__ == "__main__":
    main()

