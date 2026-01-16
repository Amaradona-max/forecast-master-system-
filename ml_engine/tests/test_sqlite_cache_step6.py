from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ml_engine.cache.sqlite_cache import SqliteCache


def test_sqlite_cache_set_get_and_expiry(tmp_path) -> None:
    db = tmp_path / "cache.sqlite"
    cache = SqliteCache(db_path=db)
    now = datetime.now(timezone.utc)

    cache.set(
        cache_key="k1",
        championship="serie_a",
        match_id="m1",
        matchday=1,
        payload={"probabilities": {"home_win": 0.5, "draw": 0.2, "away_win": 0.3}},
        ttl_seconds=60,
        model_version="mv",
        feature_version="fv",
        calibrator_version="cv",
        inputs_hash="ih",
        now_utc=now,
    )

    hit = cache.get(cache_key="k1", now_utc=now)
    assert hit is not None
    assert hit.payload.get("probabilities", {}).get("home_win") == 0.5

    later = now + timedelta(seconds=61)
    hit2 = cache.get(cache_key="k1", now_utc=later)
    assert hit2 is None

