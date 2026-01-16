from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_gateway.app.local_files import load_calendar_fixtures
from api_gateway.app.services import PredictionService
from api_gateway.app.settings import settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=str, required=True)
    ap.add_argument("--matchday", type=int, required=True)
    ap.add_argument("--calendar-file", type=str, default=str(settings.local_calendar_filename))
    ap.add_argument("--local-data-dir", type=str, default=str(settings.local_data_dir))
    args = ap.parse_args()

    champ = str(args.league).strip()
    md = int(args.matchday)
    base_dir = Path(str(args.local_data_dir)).resolve()
    cal_file = str(args.calendar_file)

    predictor = PredictionService()
    now_dt = datetime.now(timezone.utc)
    fixtures = load_calendar_fixtures(base_dir=base_dir, calendar_filename=cal_file, championship=champ, now_utc=now_dt)
    targets = [f for f in fixtures if isinstance(f.matchday, int) and int(f.matchday) == md]

    t0 = time.time()
    ok = 0
    fail = 0
    for i, f in enumerate(targets):
        match_id = f"{champ}_local_{md}_{i:04d}"
        ctx: dict[str, Any] = {"matchday": int(md)}
        if isinstance(f.source, dict):
            ctx["source"] = dict(f.source)
        try:
            _ = predictor.predict_match(
                championship=champ,
                match_id=match_id,
                home_team=f.home_team,
                away_team=f.away_team,
                status="PREMATCH" if f.status == "FINISHED" else f.status,
                kickoff_unix=f.kickoff_unix,
                context=ctx,
            )
            ok += 1
        except Exception:
            fail += 1

    dt = time.time() - t0
    print({"league": champ, "matchday": md, "fixtures": len(targets), "cached": ok, "failed": fail, "seconds": round(dt, 3)})


if __name__ == "__main__":
    main()

