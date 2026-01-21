from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_gateway.app.historical_ratings import (
    HistoricalMatch,
    fetch_finished_matches_for_range_football_data,
)


@dataclass(frozen=True)
class TeamFormRow:
    pts_last5: int
    gf_last5: int
    ga_last5: int
    n_used: int
    asof_unix: float


def _points(hg: int, ag: int, home: bool) -> int:
    if hg == ag:
        return 1
    if home:
        return 3 if hg > ag else 0
    return 3 if ag > hg else 0


def build_team_form_payload(
    *,
    championship_matches: dict[str, list[HistoricalMatch]],
    asof_unix: float,
    window: int = 5,
    source: str = "football_data",
) -> dict[str, Any]:
    champs: dict[str, Any] = {}

    for champ, matches in championship_matches.items():
        team_games: dict[str, list[tuple[int, int, int]]] = {}
        for m in matches:
            if m.kickoff_unix >= asof_unix:
                continue
            ph = _points(m.home_goals, m.away_goals, True)
            team_games.setdefault(m.home_team, []).append((ph, int(m.home_goals), int(m.away_goals)))
            pa = _points(m.home_goals, m.away_goals, False)
            team_games.setdefault(m.away_team, []).append((pa, int(m.away_goals), int(m.home_goals)))

        teams_out: dict[str, Any] = {}
        for team, rows in team_games.items():
            if not rows:
                continue
            last = rows[-window:]
            pts = sum(x[0] for x in last)
            gf = sum(x[1] for x in last)
            ga = sum(x[2] for x in last)
            teams_out[team] = {
                "pts_last5": int(pts),
                "gf_last5": int(gf),
                "ga_last5": int(ga),
                "n_used": int(len(last)),
                "asof_unix": float(asof_unix),
            }

        champs[str(champ)] = {
            "teams": teams_out,
            "asof_unix": float(asof_unix),
            "n_matches_used": int(sum(1 for m in matches if m.kickoff_unix < asof_unix)),
        }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "asof_utc": datetime.fromtimestamp(asof_unix, tz=timezone.utc).isoformat(),
        "generated_at_unix": time.time(),
        "meta": {"model": "team_form_last5_v1", "source": str(source), "window": int(window)},
        "championships": champs,
    }


def write_form_file(*, path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def rebuild_team_form_from_football_data(
    *,
    codes: dict[str, str],
    api_base_url: str,
    api_key: str,
    season_start_utc_iso: str,
    season_end_utc_iso: str,
    form_path: str,
    window: int = 5,
) -> None:
    now0 = time.time()
    now_dt = datetime.fromtimestamp(now0, tz=timezone.utc)

    def _parse_iso(s: str) -> datetime | None:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    start_dt = _parse_iso(season_start_utc_iso) or datetime(2025, 8, 1, tzinfo=timezone.utc)
    end_dt = _parse_iso(season_end_utc_iso) or datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)

    to_dt = now_dt if now_dt <= end_dt else end_dt
    from_day = start_dt.date().isoformat()
    to_day = to_dt.date().isoformat()

    championship_matches: dict[str, list[HistoricalMatch]] = {}
    total = 0
    for champ, code in codes.items():
        try:
            ms = fetch_finished_matches_for_range_football_data(
                championship=str(champ),
                competition_code=str(code),
                date_from_iso=from_day,
                date_to_iso=to_day,
                api_base_url=str(api_base_url),
                api_key=str(api_key),
            )
        except Exception:
            ms = []
        total += len(ms)
        championship_matches[str(champ)] = ms

    if total <= 0:
        return

    payload = build_team_form_payload(
        championship_matches=championship_matches,
        asof_unix=now0,
        window=int(window),
        source="football_data",
    )
    write_form_file(path=str(form_path), payload=payload)
