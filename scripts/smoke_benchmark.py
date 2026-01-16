import time

from ml_engine.ensemble_predictor.service import EnsemblePredictorService


def main() -> None:
    svc = EnsemblePredictorService()
    ctx = {"matchday": 12}

    svc.predict(championship="serie_a", home_team="Inter", away_team="Milan", status="PREMATCH", context=ctx)

    n = 100
    t0 = time.perf_counter()
    for _ in range(n):
        svc.predict(championship="serie_a", home_team="Inter", away_team="Milan", status="PREMATCH", context=ctx)
    t1 = time.perf_counter()

    ms = (t1 - t0) * 1000 / n
    print(f"Avg predict latency over {n} calls: {ms:.2f} ms")


if __name__ == "__main__":
    main()

