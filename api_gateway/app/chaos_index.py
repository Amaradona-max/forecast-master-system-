from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = float(lo)
    if v != v:
        v = float(lo)
    return max(float(lo), min(float(hi), float(v)))


@dataclass(frozen=True)
class TeamDyn:
    recent_kickoffs: list[float]
    points_std_last10: float


def _extract_team_dyn(champ_block: dict[str, Any], team: str) -> TeamDyn | None:
    teams = champ_block.get("teams")
    if not isinstance(teams, dict):
        return None
    row = teams.get(team)
    if not isinstance(row, dict):
        return None
    ks = row.get("recent_kickoffs")
    if not isinstance(ks, list):
        ks = []
    kickoffs = [float(x) for x in ks if isinstance(x, (int, float))]
    pts_std = row.get("points_std_last10")
    try:
        pts_std_f = float(pts_std)
    except Exception:
        pts_std_f = 0.0
    return TeamDyn(recent_kickoffs=kickoffs, points_std_last10=float(pts_std_f))


def _count_in_window(kickoffs: list[float], *, kickoff_unix: float, window_days: int) -> int:
    lo = float(kickoff_unix) - float(window_days) * 86400.0
    hi = float(kickoff_unix)
    return sum(1 for k in kickoffs if lo <= float(k) < hi)


def _last_before(kickoffs: list[float], *, kickoff_unix: float) -> float | None:
    prev = [k for k in kickoffs if float(k) < float(kickoff_unix)]
    if not prev:
        return None
    return float(max(prev))


def compute_chaos(
    *,
    team_dynamics_payload: dict[str, Any] | None,
    championship: str,
    home_team: str,
    away_team: str,
    kickoff_unix: float | None,
    best_prob: float | None = None,
) -> dict[str, Any] | None:
    if kickoff_unix is None or not isinstance(kickoff_unix, (int, float)):
        return None
    if not isinstance(team_dynamics_payload, dict):
        return None

    champs = team_dynamics_payload.get("championships")
    if not isinstance(champs, dict):
        return None

    champ_block = champs.get(str(championship))
    if not isinstance(champ_block, dict):
        return None

    hd = _extract_team_dyn(champ_block, str(home_team))
    ad = _extract_team_dyn(champ_block, str(away_team))
    if hd is None or ad is None:
        return None

    h_last = _last_before(hd.recent_kickoffs, kickoff_unix=float(kickoff_unix))
    a_last = _last_before(ad.recent_kickoffs, kickoff_unix=float(kickoff_unix))

    h_rest = None if h_last is None else (float(kickoff_unix) - float(h_last)) / 86400.0
    a_rest = None if a_last is None else (float(kickoff_unix) - float(a_last)) / 86400.0

    h7 = _count_in_window(hd.recent_kickoffs, kickoff_unix=float(kickoff_unix), window_days=7)
    a7 = _count_in_window(ad.recent_kickoffs, kickoff_unix=float(kickoff_unix), window_days=7)
    h10 = _count_in_window(hd.recent_kickoffs, kickoff_unix=float(kickoff_unix), window_days=10)
    a10 = _count_in_window(ad.recent_kickoffs, kickoff_unix=float(kickoff_unix), window_days=10)

    flags: list[str] = []
    score = 0.0

    if h_rest is not None and a_rest is not None:
        rest_gap = abs(float(h_rest) - float(a_rest))
        if rest_gap >= 3.0:
            score += 35
            flags.append("rest_gap_3d")
        elif rest_gap >= 2.0:
            score += 25
            flags.append("rest_gap_2d")
        elif rest_gap >= 1.5:
            score += 15
            flags.append("rest_gap_1_5d")
    else:
        rest_gap = None

    def low_rest(rest: float | None, team: str) -> None:
        nonlocal score
        if rest is None:
            return
        if rest < 2.0:
            score += 25
            flags.append(f"{team}_rest_lt2d")
        elif rest < 3.0:
            score += 15
            flags.append(f"{team}_rest_lt3d")

    low_rest(h_rest, "home")
    low_rest(a_rest, "away")

    cong_gap10 = abs(int(h10) - int(a10))
    if cong_gap10 >= 3:
        score += 35
        flags.append("congestion_gap10_3")
    elif cong_gap10 >= 2:
        score += 25
        flags.append("congestion_gap10_2")
    elif cong_gap10 >= 1:
        score += 10
        flags.append("congestion_gap10_1")

    if h7 >= 3:
        score += 15
        flags.append("home_3matches_7d")
    if a7 >= 3:
        score += 15
        flags.append("away_3matches_7d")

    vol_h = float(hd.points_std_last10)
    vol_a = float(ad.points_std_last10)
    vol_max = max(vol_h, vol_a)

    if vol_max >= 1.30:
        score += 20
        flags.append("volatility_high")
    elif vol_max >= 1.10:
        score += 15
        flags.append("volatility_med")

    if vol_h >= 1.10 and vol_a >= 1.10:
        score += 10
        flags.append("both_volatile")

    chaos = _clamp(score, 0.0, 100.0)

    try:
        bp = float(best_prob) if best_prob is not None else None
    except Exception:
        bp = None
    upset_watch = bool(chaos >= 70.0 and (bp is None or bp < 0.62))

    return {
        "index": float(chaos),
        "upset_watch": bool(upset_watch),
        "flags": flags,
        "features": {
            "home_rest_days": None if h_rest is None else float(h_rest),
            "away_rest_days": None if a_rest is None else float(a_rest),
            "rest_gap_days": None if rest_gap is None else float(rest_gap),
            "home_matches_last7d": int(h7),
            "away_matches_last7d": int(a7),
            "home_matches_last10d": int(h10),
            "away_matches_last10d": int(a10),
            "home_points_std_last10": float(vol_h),
            "away_points_std_last10": float(vol_a),
        },
    }
