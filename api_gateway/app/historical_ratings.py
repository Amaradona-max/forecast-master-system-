from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HistoricalMatch:
    championship: str
    kickoff_unix: float
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


def _http_get_json(url: str, *, headers: dict[str, str]) -> Any:
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _parse_kickoff_unix(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    return None


def _safe_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        try:
            return int(v.strip())
        except Exception:
            return None
    return None


def fetch_finished_matches_for_season(
    *,
    championship: str,
    league_id: int,
    season_year: int,
    api_base_url: str,
    api_key: str,
) -> list[HistoricalMatch]:
    headers = {"x-apisports-key": api_key}
    qs = urlencode({"league": league_id, "season": season_year, "timezone": "UTC"})
    url = f"{api_base_url.rstrip('/')}/fixtures?{qs}"
    payload = _http_get_json(url, headers=headers)
    items = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    out: list[HistoricalMatch] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        fixture = it.get("fixture") if isinstance(it.get("fixture"), dict) else {}
        teams = it.get("teams") if isinstance(it.get("teams"), dict) else {}
        goals = it.get("goals") if isinstance(it.get("goals"), dict) else {}
        status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}

        short = str(status.get("short") or "").upper()
        if short not in {"FT", "AET", "PEN"}:
            continue

        kickoff_unix = _parse_kickoff_unix(fixture.get("date"))
        if kickoff_unix is None:
            continue

        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        home_team = str(home.get("name") or "").strip()
        away_team = str(away.get("name") or "").strip()
        if not home_team or not away_team:
            continue

        hg = _safe_int(goals.get("home"))
        ag = _safe_int(goals.get("away"))
        if hg is None or ag is None:
            continue

        out.append(
            HistoricalMatch(
                championship=championship,
                kickoff_unix=float(kickoff_unix),
                home_team=home_team,
                away_team=away_team,
                home_goals=int(hg),
                away_goals=int(ag),
            )
        )
    out.sort(key=lambda m: m.kickoff_unix)
    return out


def _expected_score(r_home: float, r_away: float, home_adv_points: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_away - (r_home + home_adv_points)) / 400.0))


def _k_factor(goal_diff: int) -> float:
    g = abs(int(goal_diff))
    if g <= 1:
        return 20.0
    if g == 2:
        return 26.0
    if g == 3:
        return 30.0
    return 32.0


def build_elo_strengths(
    *,
    matches: list[HistoricalMatch],
    asof_unix: float,
    home_adv_points: float = 55.0,
) -> dict[str, dict[str, Any]]:
    ratings: dict[str, float] = {}
    used = 0
    for m in matches:
        if m.kickoff_unix >= asof_unix:
            continue
        r_home = ratings.get(m.home_team, 1500.0)
        r_away = ratings.get(m.away_team, 1500.0)
        exp_home = _expected_score(r_home, r_away, home_adv_points)
        if m.home_goals > m.away_goals:
            score_home = 1.0
        elif m.home_goals == m.away_goals:
            score_home = 0.5
        else:
            score_home = 0.0
        k = _k_factor(m.home_goals - m.away_goals)
        delta = k * (score_home - exp_home)
        ratings[m.home_team] = r_home + delta
        ratings[m.away_team] = r_away - delta
        used += 1

    if not ratings:
        return {"teams": {}, "n_matches_used": 0, "asof_unix": asof_unix}

    mean_rating = sum(ratings.values()) / len(ratings)
    teams_out: dict[str, Any] = {}
    for team, elo in ratings.items():
        z = (elo - mean_rating) / 400.0
        strength = max(min(z * 0.9, 0.9), -0.9)
        teams_out[team] = {"elo": float(elo), "strength": float(strength)}

    return {"teams": teams_out, "n_matches_used": used, "asof_unix": asof_unix, "mean_elo": float(mean_rating)}


def write_ratings_file(*, path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_ratings_payload(
    *,
    championship_matches: dict[str, list[HistoricalMatch]],
    asof_unix: float,
    source: str,
) -> dict[str, Any]:
    champs: dict[str, Any] = {}
    for champ, matches in championship_matches.items():
        champs[champ] = build_elo_strengths(matches=matches, asof_unix=asof_unix)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "asof_utc": datetime.fromtimestamp(asof_unix, tz=timezone.utc).isoformat(),
        "championships": champs,
        "meta": {"model": "elo_strength_v1", "source": str(source)},
        "generated_at_unix": time.time(),
    }
