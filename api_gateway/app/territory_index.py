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
        for k, v in headers.items():
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


def _stat_map(stats_payload: Any) -> dict[str, dict[str, Any]]:
    """
    API-Football fixtures/statistics returns:
    {
      "response": [
        {"team": {...}, "statistics": [{"type":"Ball Possession","value":"55%"}, ...]},
        {"team": {...}, "statistics": [...]}
      ]
    }
    We normalize to:
      { "HOME_TEAM_NAME": {"ball_possession": 55.0, "attacks": 123, "dangerous_attacks": 48, ...}, ... }
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
        m: dict[str, Any] = {}
        for s in stats_list:
            if not isinstance(s, dict):
                continue
            typ = str(s.get("type") or "").strip().lower()
            val = s.get("value")
            if not typ:
                continue
            if typ in {"ball possession", "possession"}:
                m["possession_pct"] = _parse_pct(val)
            elif typ in {"dangerous attacks", "dangerous_attacks"}:
                m["dangerous_attacks"] = _parse_int(val)
            elif typ in {"attacks", "total attacks"}:
                m["attacks"] = _parse_int(val)
            elif typ in {"total shots", "shots total"}:
                m["shots_total"] = _parse_int(val)
            elif typ in {"shots on goal", "shots on target"}:
                m["shots_on_goal"] = _parse_int(val)
            elif typ in {"corner kicks", "corners"}:
                m["corners"] = _parse_int(val)
        out[name] = m
    return out


def _proxy_attacks(m: dict[str, Any]) -> int | None:
    attacks = m.get("attacks")
    if isinstance(attacks, int) and attacks > 0:
        return attacks

    da = m.get("dangerous_attacks")
    st = m.get("shots_total")
    co = m.get("corners")
    da_i = da if isinstance(da, int) else 0
    st_i = st if isinstance(st, int) else 0
    co_i = co if isinstance(co, int) else 0
    proxy = da_i * 2 + st_i * 3 + co_i
    if proxy <= 0:
        return None
    return int(proxy)


def _proxy_dangerous(m: dict[str, Any]) -> int | None:
    da = m.get("dangerous_attacks")
    if isinstance(da, int) and da >= 0:
        return da

    sog = m.get("shots_on_goal")
    st = m.get("shots_total")
    co = m.get("corners")
    sog_i = sog if isinstance(sog, int) else 0
    st_i = st if isinstance(st, int) else 0
    co_i = co if isinstance(co, int) else 0
    proxy = sog_i * 2 + st_i + int(round(co_i / 2))
    if proxy <= 0:
        return None
    return int(proxy)


@dataclass(frozen=True)
class TeamTPX:
    team: str
    off_raw: float
    def_raw: float
    n_matches: int


def compute_tpx_for_fixture(*, home_team: str, away_team: str, stats_payload: Any) -> tuple[TeamTPX | None, TeamTPX | None]:
    stats = _stat_map(stats_payload)
    h = stats.get(home_team)
    a = stats.get(away_team)
    if not isinstance(h, dict) or not isinstance(a, dict):
        return (None, None)

    h_pos = _parse_pct(h.get("possession_pct"))
    a_pos = _parse_pct(a.get("possession_pct"))
    if h_pos is None or a_pos is None:
        return (None, None)

    h_att = _proxy_attacks(h)
    a_att = _proxy_attacks(a)
    h_da = _proxy_dangerous(h)
    a_da = _proxy_dangerous(a)
    if h_att is None or a_att is None or h_da is None or a_da is None:
        return (None, None)

    h_att = max(int(h_att), 1)
    a_att = max(int(a_att), 1)
    h_da = max(int(h_da), 0)
    a_da = max(int(a_da), 0)

    h_quality = float(h_da) / float(h_att)
    a_quality = float(a_da) / float(a_att)
    h_off = float(h_pos) * h_quality
    a_off = float(a_pos) * a_quality

    h_opp_unsucc = float(a_att - a_da) / float(a_att)
    a_opp_unsucc = float(h_att - h_da) / float(h_att)
    h_def = float(a_pos) * h_opp_unsucc
    a_def = float(h_pos) * a_opp_unsucc

    return (
        TeamTPX(team=home_team, off_raw=h_off, def_raw=h_def, n_matches=1),
        TeamTPX(team=away_team, off_raw=a_off, def_raw=a_def, n_matches=1),
    )


def _minmax_scale(values: dict[str, float]) -> dict[str, float]:
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
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        out[k] = 100.0 * (fv - lo) / (hi - lo)
    return out


def build_team_tpx_index(
    *,
    championship: str,
    fixtures: list[dict[str, Any]],
    fetch_statistics: Any,
    min_matches: int = 6,
) -> dict[str, Any]:
    """
    fixtures: list of normalized fixture dicts with:
      { "fixture_id": int, "home_team": str, "away_team": str, "status": str, "kickoff_unix": float }
    fetch_statistics: callable(fixture_id:int)->payload
    """
    acc_off: dict[str, float] = {}
    acc_def: dict[str, float] = {}
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
        h_tpx, a_tpx = compute_tpx_for_fixture(home_team=home, away_team=away, stats_payload=payload)
        if h_tpx is None or a_tpx is None:
            continue

        acc_off[home] = float(acc_off.get(home, 0.0)) + float(h_tpx.off_raw)
        acc_def[home] = float(acc_def.get(home, 0.0)) + float(h_tpx.def_raw)
        counts[home] = int(counts.get(home, 0)) + 1

        acc_off[away] = float(acc_off.get(away, 0.0)) + float(a_tpx.off_raw)
        acc_def[away] = float(acc_def.get(away, 0.0)) + float(a_tpx.def_raw)
        counts[away] = int(counts.get(away, 0)) + 1

    avg_off: dict[str, float] = {}
    avg_def: dict[str, float] = {}
    for team, n in counts.items():
        if n <= 0:
            continue
        avg_off[team] = float(acc_off.get(team, 0.0)) / float(n)
        avg_def[team] = float(acc_def.get(team, 0.0)) / float(n)

    scaled_off = _minmax_scale(avg_off)
    scaled_def = _minmax_scale(avg_def)

    teams: dict[str, Any] = {}
    for team in sorted(set(list(counts.keys()) + list(avg_off.keys()) + list(avg_def.keys())), key=lambda x: x.lower()):
        n = int(counts.get(team, 0))
        if n < int(min_matches):
            continue
        teams[team] = {
            "off_index": round(float(scaled_off.get(team, 50.0)), 2),
            "def_index": round(float(scaled_def.get(team, 50.0)), 2),
            "n_matches": n,
            "off_raw_avg": round(float(avg_off.get(team, 0.0)), 4),
            "def_raw_avg": round(float(avg_def.get(team, 0.0)), 4),
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


def _clamp(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = float(lo)
    if v != v:
        v = float(lo)
    return max(float(lo), min(float(hi), float(v)))


def _pct(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        f = float(v)
        if 0.0 <= f <= 100.0:
            return f
        return None
    if isinstance(v, str):
        s = v.strip().replace("%", "").strip()
        try:
            f = float(s)
        except Exception:
            return None
        if 0.0 <= f <= 100.0:
            return float(f)
    return None


def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
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


@dataclass(frozen=True)
class TerritoryMatchRow:
    championship: str
    kickoff_unix: float
    home_team: str
    away_team: str
    home_possession_pct: float
    away_possession_pct: float
    home_attacks: int
    away_attacks: int
    home_dangerous_attacks: int
    away_dangerous_attacks: int


def parse_api_football_stats_row(*, fixture_item: dict[str, Any], stats_payload: Any, championship: str) -> TerritoryMatchRow | None:
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

    pos_names = {"ball possession", "possession"}
    attacks_names = {"total attacks", "attacks"}
    dang_names = {"dangerous attacks", "dangerous attack"}

    h_pos = _pct(_find_stat(h_stats, names=pos_names))
    a_pos = _pct(_find_stat(a_stats, names=pos_names))
    h_att = _int(_find_stat(h_stats, names=attacks_names))
    a_att = _int(_find_stat(a_stats, names=attacks_names))
    h_dang = _int(_find_stat(h_stats, names=dang_names))
    a_dang = _int(_find_stat(a_stats, names=dang_names))

    if h_pos is None or a_pos is None or h_att is None or a_att is None or h_dang is None or a_dang is None:
        return None

    return TerritoryMatchRow(
        championship=str(championship),
        kickoff_unix=float(kickoff_unix),
        home_team=home_team,
        away_team=away_team,
        home_possession_pct=float(h_pos),
        away_possession_pct=float(a_pos),
        home_attacks=int(h_att),
        away_attacks=int(a_att),
        home_dangerous_attacks=int(h_dang),
        away_dangerous_attacks=int(a_dang),
    )


def _share(a: float, b: float) -> float:
    s = float(a) + float(b)
    if s <= 0:
        return 0.5
    return _clamp(float(a) / s, 0.0, 1.0)


def _off_score(*, pos_pct: float, attacks: int, opp_attacks: int, dang: int, opp_dang: int) -> float:
    pos_share = _clamp(float(pos_pct) / 100.0, 0.0, 1.0)
    att_share = _share(float(attacks), float(opp_attacks))
    dang_share = _share(float(dang), float(opp_dang))
    return 100.0 * _clamp((0.45 * pos_share) + (0.25 * att_share) + (0.30 * dang_share), 0.0, 1.0)


def _def_score(*, opp_pos_pct: float, opp_attacks: int, opp_dang: int) -> float:
    pressure = _clamp(float(opp_pos_pct) / 100.0, 0.0, 1.0)
    dang_rate = float(opp_dang) / float(max(1, int(opp_attacks)))
    containment = 1.0 - _clamp(dang_rate / 0.35, 0.0, 1.0)
    base = (0.62 * containment) + (0.38 * (1.0 - pressure))
    return 100.0 * _clamp(base, 0.0, 1.0)


def build_team_territory_index_payload(
    *,
    rows: list[TerritoryMatchRow],
    lookback_days: int,
    min_matches: int,
    provider: str,
) -> dict[str, Any]:
    by_champ: dict[str, list[TerritoryMatchRow]] = {}
    for r in rows:
        by_champ.setdefault(str(r.championship), []).append(r)

    champs_out: dict[str, Any] = {}
    for champ, items in by_champ.items():
        items.sort(key=lambda x: x.kickoff_unix)
        teams: dict[str, dict[str, list[float] | float]] = {}
        last_kick: dict[str, float] = {}

        for m in items:
            h_off = _off_score(
                pos_pct=m.home_possession_pct,
                attacks=m.home_attacks,
                opp_attacks=m.away_attacks,
                dang=m.home_dangerous_attacks,
                opp_dang=m.away_dangerous_attacks,
            )
            a_off = _off_score(
                pos_pct=m.away_possession_pct,
                attacks=m.away_attacks,
                opp_attacks=m.home_attacks,
                dang=m.away_dangerous_attacks,
                opp_dang=m.home_dangerous_attacks,
            )
            h_def = _def_score(opp_pos_pct=m.away_possession_pct, opp_attacks=m.away_attacks, opp_dang=m.away_dangerous_attacks)
            a_def = _def_score(opp_pos_pct=m.home_possession_pct, opp_attacks=m.home_attacks, opp_dang=m.home_dangerous_attacks)

            teams.setdefault(m.home_team, {"off": [], "def": []})
            teams.setdefault(m.away_team, {"off": [], "def": []})
            (teams[m.home_team]["off"]).append(float(h_off))  # type: ignore[index]
            (teams[m.home_team]["def"]).append(float(h_def))  # type: ignore[index]
            (teams[m.away_team]["off"]).append(float(a_off))  # type: ignore[index]
            (teams[m.away_team]["def"]).append(float(a_def))  # type: ignore[index]
            last_kick[m.home_team] = float(m.kickoff_unix)
            last_kick[m.away_team] = float(m.kickoff_unix)

        teams_out: dict[str, Any] = {}
        for team, agg in teams.items():
            off_list = agg.get("off") if isinstance(agg, dict) else None
            def_list = agg.get("def") if isinstance(agg, dict) else None
            if not isinstance(off_list, list) or not isinstance(def_list, list):
                continue
            n = min(len(off_list), len(def_list))
            if n < int(min_matches):
                continue
            off_avg = sum(float(x) for x in off_list[:n]) / float(n)
            def_avg = sum(float(x) for x in def_list[:n]) / float(n)
            teams_out[str(team)] = {
                "off_index": float(_clamp(off_avg, 0.0, 100.0)),
                "def_index": float(_clamp(def_avg, 0.0, 100.0)),
                "n_used": int(n),
                "last_kickoff_unix": float(last_kick.get(team) or 0.0),
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
            "model": "team_territory_index_v2",
            "provider": str(provider),
            "lookback_days": int(lookback_days),
            "min_matches": int(min_matches),
        },
        "championships": champs_out,
    }


def write_territory_index_file(*, path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
