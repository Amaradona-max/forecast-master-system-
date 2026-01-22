from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from api_gateway.app.historical_ratings import HistoricalMatch, fetch_finished_matches_for_range_football_data


def _points(hg: int, ag: int, home: bool) -> int:
    if int(hg) == int(ag):
        return 1
    if bool(home):
        return 3 if int(hg) > int(ag) else 0
    return 3 if int(ag) > int(hg) else 0


def _std(values: list[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return float(var**0.5)


def build_team_dynamics_payload(
    *,
    championship_matches: dict[str, list[HistoricalMatch]],
    asof_unix: float,
    recent_kickoffs_limit: int = 25,
    std_window: int = 10,
    source: str = "football_data",
) -> dict[str, Any]:
    champs: dict[str, Any] = {}

    for champ, matches in championship_matches.items():
        team_games: dict[str, list[tuple[float, int]]] = {}

        for m in matches:
            if m.kickoff_unix >= asof_unix:
                continue
            ph = _points(m.home_goals, m.away_goals, True)
            pa = _points(m.home_goals, m.away_goals, False)

            team_games.setdefault(m.home_team, []).append((float(m.kickoff_unix), int(ph)))
            team_games.setdefault(m.away_team, []).append((float(m.kickoff_unix), int(pa)))

        teams_out: dict[str, Any] = {}
        for team, items in team_games.items():
            items.sort(key=lambda x: x[0], reverse=True)
            kickoffs = [k for (k, _p) in items[:recent_kickoffs_limit]]
            pts_last = [float(p) for (_k, p) in items[:std_window]]
            pts_std = _std(pts_last)

            teams_out[team] = {
                "recent_kickoffs": kickoffs,
                "points_std_last10": float(pts_std),
                "asof_unix": float(asof_unix),
            }

        champs[champ] = {
            "source": str(source),
            "asof_unix": float(asof_unix),
            "teams": teams_out,
        }

    return {
        "generated_at_unix": float(asof_unix),
        "generated_at_utc": datetime.fromtimestamp(float(asof_unix), tz=timezone.utc).isoformat(),
        "meta": {
            "model": "team_dynamics_v1",
            "recent_kickoffs_limit": int(recent_kickoffs_limit),
            "std_window": int(std_window),
        },
        "championships": champs,
    }


def _write_json(path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def rebuild_team_dynamics_to_file(
    *,
    championships: list[str],
    competition_codes: dict[str, str],
    api_base_url: str,
    api_key: str,
    lookback_days: int,
    per_league_limit: int,
    out_path: str,
) -> dict[str, Any] | None:
    now0 = time.time()
    date_to = datetime.fromtimestamp(now0, tz=timezone.utc).date()
    date_from = date_to - timedelta(days=int(lookback_days))

    date_from_iso = date_from.isoformat()
    date_to_iso = date_to.isoformat()

    championship_matches: dict[str, list[HistoricalMatch]] = {}

    for champ in championships:
        code = competition_codes.get(champ)
        if not code:
            continue
        try:
            ms = fetch_finished_matches_for_range_football_data(
                championship=str(champ),
                competition_code=str(code),
                date_from_iso=str(date_from_iso),
                date_to_iso=str(date_to_iso),
                api_base_url=str(api_base_url),
                api_key=str(api_key),
            )
        except Exception:
            ms = []
        ms = sorted(ms, key=lambda m: m.kickoff_unix, reverse=True)[: int(per_league_limit)]
        championship_matches[str(champ)] = ms

    payload = build_team_dynamics_payload(championship_matches=championship_matches, asof_unix=float(now0))
    _write_json(out_path, payload)
    return payload


def rebuild_team_dynamics_from_football_data(
    *,
    codes: dict[str, str],
    api_base_url: str,
    api_key: str,
    out_path: str,
    lookback_days: int = 60,
    per_league_limit: int = 1200,
) -> dict[str, Any] | None:
    return rebuild_team_dynamics_to_file(
        championships=[str(k) for k in (codes or {}).keys()],
        competition_codes={str(k): str(v) for k, v in (codes or {}).items()},
        api_base_url=str(api_base_url),
        api_key=str(api_key),
        lookback_days=int(lookback_days),
        per_league_limit=int(per_league_limit),
        out_path=str(out_path),
    )
