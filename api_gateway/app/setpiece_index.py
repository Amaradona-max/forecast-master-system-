from __future__ import annotations

import json
import math
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


try:
    import certifi  # type: ignore

    _CERTIFI_CAFILE = certifi.where()
except Exception:
    _CERTIFI_CAFILE = None


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if _CERTIFI_CAFILE:
        try:
            ctx.load_verify_locations(_CERTIFI_CAFILE)
        except Exception:
            pass
    return ctx


def _http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 25) -> Any:
    req = Request(url)
    if headers:
        for k, v in (headers or {}).items():
            req.add_header(k, v)
    with urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return json.loads(raw)


def _parse_pct(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
        if 0.0 <= v <= 100.0:
            return v
        if 0.0 <= v <= 1.0:
            return v * 100.0
        return None
    s = str(x).strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        v = float(s.replace(",", "."))
    except Exception:
        return None
    if 0.0 <= v <= 100.0:
        return v
    if 0.0 <= v <= 1.0:
        return v * 100.0
    return None


def _parse_int(x: Any) -> int | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        if math.isfinite(x):
            return int(round(x))
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _find_stat(stats: Any, *, names: set[str]) -> Any | None:
    if not isinstance(stats, list):
        return None
    for it in stats:
        if not isinstance(it, dict):
            continue
        t = str(it.get("type") or "").strip().lower()
        if not t:
            continue
        if t in names:
            return it.get("value")
    return None


def _stat_map(stats_payload: Any) -> dict[str, dict[str, Any]]:
    """
    Normalizza API-Football fixtures/statistics in:
      { "Team Name": {"corners": int|None, "free_kicks": int|None, "possession_pct": float|None}, ... }
    """
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(stats_payload, dict):
        return out
    items = stats_payload.get("response")
    if not isinstance(items, list):
        return out

    for it in items:
        if not isinstance(it, dict):
            continue
        team = it.get("team") or {}
        name = str((team.get("name") if isinstance(team, dict) else "") or "").strip()
        if not name:
            continue

        stats_list = it.get("statistics")
        if not isinstance(stats_list, list):
            continue

        m: dict[str, Any] = {"corners": None, "free_kicks": None, "possession_pct": None}
        for s in stats_list:
            if not isinstance(s, dict):
                continue
            typ = str(s.get("type") or "").strip().lower()
            val = s.get("value")
            if not typ:
                continue

            if typ in {"corner kicks", "corners"}:
                m["corners"] = _parse_int(val)
            elif typ in {"free kicks", "freekicks"}:
                m["free_kicks"] = _parse_int(val)
            elif typ in {"ball possession", "possession"}:
                m["possession_pct"] = _parse_pct(val)

        out[name] = m
    return out


def _minmax_scale(values: dict[str, float], *, invert: bool = False) -> dict[str, float]:
    if not values:
        return {}
    xs = [float(v) for v in values.values() if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not xs:
        return {k: 50.0 for k in values.keys()}
    lo = min(xs)
    hi = max(xs)
    if hi - lo < 1e-9:
        return {k: 50.0 for k in values.keys()}

    out: dict[str, float] = {}
    for k, v in values.items():
        fv = float(v) if math.isfinite(float(v)) else lo
        z = (fv - lo) / (hi - lo)
        if invert:
            z = 1.0 - z
        out[k] = 100.0 * z
    return out


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = float(lo)
    if not math.isfinite(v):
        v = float(lo)
    return max(float(lo), min(float(hi), float(v)))


@dataclass(frozen=True)
class TeamSPX:
    team: str
    off_raw: float
    conceded_raw: float
    n_matches: int


def compute_spx_for_fixture(*, home_team: str, away_team: str, stats_payload: Any) -> tuple[TeamSPX | None, TeamSPX | None]:
    stats = _stat_map(stats_payload)
    h = stats.get(home_team)
    a = stats.get(away_team)
    if not isinstance(h, dict) or not isinstance(a, dict):
        return (None, None)

    h_c = _parse_int(h.get("corners"))
    a_c = _parse_int(a.get("corners"))
    if h_c is None or a_c is None:
        return (None, None)

    h_fk = _parse_int(h.get("free_kicks"))
    a_fk = _parse_int(a.get("free_kicks"))

    fk_w = 0.6
    h_off = float(max(h_c, 0)) + fk_w * float(max(h_fk or 0, 0))
    a_off = float(max(a_c, 0)) + fk_w * float(max(a_fk or 0, 0))

    h_conc = float(max(a_c, 0)) + fk_w * float(max(a_fk or 0, 0))
    a_conc = float(max(h_c, 0)) + fk_w * float(max(h_fk or 0, 0))

    return (
        TeamSPX(team=home_team, off_raw=h_off, conceded_raw=h_conc, n_matches=1),
        TeamSPX(team=away_team, off_raw=a_off, conceded_raw=a_conc, n_matches=1),
    )


def build_team_spx_index(
    *,
    championship: str,
    fixtures: list[dict[str, Any]],
    fetch_statistics: Any,
    min_matches: int = 6,
) -> dict[str, Any]:
    acc_off: dict[str, float] = {}
    acc_conc: dict[str, float] = {}
    counts: dict[str, int] = {}

    for fx in fixtures:
        fid = fx.get("fixture_id")
        home = str(fx.get("home_team") or "").strip()
        away = str(fx.get("away_team") or "").strip()
        status = str(fx.get("status") or "").upper()

        if not isinstance(fid, int) or fid <= 0:
            continue
        if not home or not away:
            continue
        if status not in {"FT", "AET", "PEN", "FINISHED"}:
            continue

        payload = fetch_statistics(int(fid))
        h, a = compute_spx_for_fixture(home_team=home, away_team=away, stats_payload=payload)
        if h is None or a is None:
            continue

        for t in (h, a):
            acc_off[t.team] = float(acc_off.get(t.team, 0.0)) + float(t.off_raw)
            acc_conc[t.team] = float(acc_conc.get(t.team, 0.0)) + float(t.conceded_raw)
            counts[t.team] = int(counts.get(t.team, 0)) + 1

    avg_off: dict[str, float] = {}
    avg_conc: dict[str, float] = {}
    for team, n in counts.items():
        if n <= 0:
            continue
        avg_off[team] = float(acc_off.get(team, 0.0)) / float(n)
        avg_conc[team] = float(acc_conc.get(team, 0.0)) / float(n)

    off_idx = _minmax_scale(avg_off, invert=False)
    def_idx = _minmax_scale(avg_conc, invert=True)

    teams: dict[str, Any] = {}
    for team in sorted(counts.keys(), key=lambda x: x.lower()):
        n = int(counts.get(team, 0))
        if n < int(min_matches):
            continue
        teams[team] = {
            "off_index": round(float(off_idx.get(team, 50.0)), 2),
            "def_index": round(float(def_idx.get(team, 50.0)), 2),
            "n_matches": n,
            "off_raw_avg": round(float(avg_off.get(team, 0.0)), 4),
            "conceded_raw_avg": round(float(avg_conc.get(team, 0.0)), 4),
        }

    return {
        "championship": str(championship),
        "teams": teams,
        "meta": {
            "min_matches": int(min_matches),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    }


def api_football_fetch_fixture_statistics(*, base_url: str, api_key: str, fixture_id: int) -> Any:
    qs = urlencode({"fixture": int(fixture_id)})
    url = f"{base_url.rstrip('/')}/fixtures/statistics?{qs}"
    headers = {"x-apisports-key": str(api_key)}
    return _http_get_json(url, headers=headers, timeout=25)


@dataclass(frozen=True)
class SetPieceMatchRow:
    championship: str
    kickoff_unix: float
    home_team: str
    away_team: str
    home_corners: int
    away_corners: int
    home_free_kicks: int | None
    away_free_kicks: int | None


def parse_api_football_setpiece_row(*, fixture_item: dict[str, Any], stats_payload: Any, championship: str) -> SetPieceMatchRow | None:
    if not isinstance(fixture_item, dict) or not isinstance(stats_payload, dict):
        return None

    fixture = fixture_item.get("fixture") if isinstance(fixture_item.get("fixture"), dict) else {}
    teams = fixture_item.get("teams") if isinstance(fixture_item.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}

    home_id = home.get("id")
    away_id = away.get("id")
    if not isinstance(home_id, (int, float)) or not isinstance(away_id, (int, float)):
        return None
    home_id_i = int(home_id)
    away_id_i = int(away_id)

    kickoff_iso = fixture.get("date")
    if not isinstance(kickoff_iso, str) or not kickoff_iso:
        return None
    try:
        kickoff_unix = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

    home_team = str(home.get("name") or "").strip()
    away_team = str(away.get("name") or "").strip()
    if not home_team or not away_team:
        return None

    resp = stats_payload.get("response")
    if not isinstance(resp, list) or not resp:
        return None

    def _team_stats(team_id: int) -> list[dict[str, Any]] | None:
        for x in resp:
            if not isinstance(x, dict):
                continue
            t = x.get("team") if isinstance(x.get("team"), dict) else {}
            tid = t.get("id")
            if isinstance(tid, (int, float)) and int(tid) == int(team_id):
                st = x.get("statistics")
                return st if isinstance(st, list) else None
        return None

    h_stats = _team_stats(home_id_i)
    a_stats = _team_stats(away_id_i)
    if not isinstance(h_stats, list) or not isinstance(a_stats, list):
        return None

    corners_names = {"corner kicks", "corners"}
    fk_names = {"free kicks", "free kick"}

    h_corners = _parse_int(_find_stat(h_stats, names=corners_names))
    a_corners = _parse_int(_find_stat(a_stats, names=corners_names))
    if h_corners is None or a_corners is None:
        return None
    if h_corners < 0 or a_corners < 0:
        return None

    h_fk = _parse_int(_find_stat(h_stats, names=fk_names))
    a_fk = _parse_int(_find_stat(a_stats, names=fk_names))
    if isinstance(h_fk, int) and h_fk < 0:
        h_fk = None
    if isinstance(a_fk, int) and a_fk < 0:
        a_fk = None

    return SetPieceMatchRow(
        championship=str(championship),
        kickoff_unix=float(kickoff_unix),
        home_team=home_team,
        away_team=away_team,
        home_corners=int(h_corners),
        away_corners=int(a_corners),
        home_free_kicks=(int(h_fk) if isinstance(h_fk, int) else None),
        away_free_kicks=(int(a_fk) if isinstance(a_fk, int) else None),
    )


def _sp_raw(*, corners: int, free_kicks: int | None) -> float:
    fk = int(free_kicks) if isinstance(free_kicks, int) else 0
    return float(int(corners)) + 0.6 * float(fk)


def build_team_setpiece_index_payload(
    *,
    rows: list[SetPieceMatchRow],
    lookback_days: int,
    min_matches: int,
    provider: str,
) -> dict[str, Any]:
    by_champ: dict[str, list[SetPieceMatchRow]] = {}
    for r in rows:
        by_champ.setdefault(str(r.championship), []).append(r)

    champs_out: dict[str, Any] = {}
    for champ, items in by_champ.items():
        items.sort(key=lambda x: x.kickoff_unix)
        teams: dict[str, dict[str, list[float]]] = {}
        last_kick: dict[str, float] = {}

        for m in items:
            h_off_raw = _sp_raw(corners=m.home_corners, free_kicks=m.home_free_kicks)
            a_off_raw = _sp_raw(corners=m.away_corners, free_kicks=m.away_free_kicks)
            h_conc_raw = _sp_raw(corners=m.away_corners, free_kicks=m.away_free_kicks)
            a_conc_raw = _sp_raw(corners=m.home_corners, free_kicks=m.home_free_kicks)

            teams.setdefault(m.home_team, {"off": [], "conceded": []})
            teams.setdefault(m.away_team, {"off": [], "conceded": []})
            teams[m.home_team]["off"].append(float(h_off_raw))
            teams[m.home_team]["conceded"].append(float(h_conc_raw))
            teams[m.away_team]["off"].append(float(a_off_raw))
            teams[m.away_team]["conceded"].append(float(a_conc_raw))
            last_kick[m.home_team] = float(m.kickoff_unix)
            last_kick[m.away_team] = float(m.kickoff_unix)

        off_avg: dict[str, float] = {}
        conceded_avg: dict[str, float] = {}
        n_used: dict[str, int] = {}
        for team, agg in teams.items():
            off_list = agg.get("off")
            conc_list = agg.get("conceded")
            if not isinstance(off_list, list) or not isinstance(conc_list, list):
                continue
            n = min(len(off_list), len(conc_list))
            if n < int(min_matches):
                continue
            off_avg[str(team)] = float(sum(float(x) for x in off_list[:n]) / float(n))
            conceded_avg[str(team)] = float(sum(float(x) for x in conc_list[:n]) / float(n))
            n_used[str(team)] = int(n)

        off_scaled = _minmax_scale(off_avg, invert=False)
        def_scaled = _minmax_scale(conceded_avg, invert=True)

        teams_out: dict[str, Any] = {}
        for team in off_avg.keys():
            teams_out[str(team)] = {
                "off_index": float(_clamp(float(off_scaled.get(team, 50.0)), 0.0, 100.0)),
                "def_index": float(_clamp(float(def_scaled.get(team, 50.0)), 0.0, 100.0)),
                "n_used": int(n_used.get(team, 0)),
                "last_kickoff_unix": float(last_kick.get(team) or 0.0),
                "off_raw_avg": float(off_avg.get(team, 0.0)),
                "conceded_raw_avg": float(conceded_avg.get(team, 0.0)),
            }

        champs_out[str(champ)] = {
            "asof_unix": float(time.time()),
            "n_matches_used": int(len(items)),
            "teams": teams_out,
        }

    now0 = time.time()
    return {
        "generated_at_unix": float(now0),
        "generated_at_utc": datetime.fromtimestamp(float(now0), tz=timezone.utc).isoformat(),
        "meta": {
            "model": "team_setpiece_index_v1",
            "provider": str(provider),
            "lookback_days": int(lookback_days),
            "min_matches": int(min_matches),
        },
        "championships": champs_out,
    }


def write_setpiece_index_file(*, path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
