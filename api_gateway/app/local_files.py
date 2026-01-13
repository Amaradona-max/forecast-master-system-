from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

from api_gateway.app.historical_ratings import HistoricalMatch


@dataclass(frozen=True)
class LocalFixture:
    championship: str
    matchday: int | None
    kickoff_unix: float | None
    home_team: str
    away_team: str
    status: str
    final_score: dict[str, int] | None = None
    source: dict[str, Any] | None = None


_HISTORY_FILENAMES: dict[str, str] = {
    "serie_a": "SerieA_Matches_2015-2025.xlsx",
    "premier_league": "PremierLeague_Matches_2015-2025.xlsx",
    "la_liga": "Liga_Matches_2015-2025.xlsx",
    "bundesliga": "Bundesliga_Matches_2015-2025.xlsx",
    "eliteserien": "Eliteserien_Matches_2015-2025.xlsx",
}

_CALENDAR_SHEETS: dict[str, str] = {
    "serie_a": "Serie A",
    "premier_league": "Premier League",
    "la_liga": "La Liga",
    "bundesliga": "Bundesliga",
    "eliteserien": "Eliteserien",
}


def local_history_path(*, base_dir: Path, championship: str) -> Path:
    fn = _HISTORY_FILENAMES.get(championship)
    if not fn:
        raise ValueError("unsupported_championship")
    return (base_dir / fn).resolve()


def local_calendar_path(*, base_dir: Path, calendar_filename: str) -> Path:
    return (base_dir / calendar_filename).resolve()


def load_historical_matches(*, base_dir: Path, championship: str, start_year: int, end_year: int) -> list[HistoricalMatch]:
    pd = _pd()
    p = local_history_path(base_dir=base_dir, championship=championship)
    if not p.exists():
        return []

    df = pd.read_excel(p, sheet_name=0, header=None)
    header_row = _find_header_row(df)
    if header_row is None:
        return []

    header = [str(x).strip() if x is not None else "" for x in df.iloc[header_row].tolist()]
    data = df.iloc[header_row + 1 :].copy()
    data.columns = header
    cols = set(str(c or "").strip() for c in data.columns)
    date_key = "Date" if "Date" in cols else "MatchDate" if "MatchDate" in cols else None
    time_key = "Time" if "Time" in cols else None
    if date_key is None:
        return []

    out: list[HistoricalMatch] = []
    for _, r in data.iterrows():
        home = str(r.get("HomeTeam") or "").strip()
        away = str(r.get("AwayTeam") or "").strip()
        if not home or not away:
            continue

        dt = _parse_datetime(date_val=r.get(date_key), time_val=r.get(time_key) if time_key else None)
        if dt is None:
            continue
        y = dt.year
        if y < int(start_year) or y > int(end_year):
            continue

        hg = _safe_int(r.get("FTHG"))
        ag = _safe_int(r.get("FTAG"))
        if hg is None or ag is None:
            continue

        out.append(
            HistoricalMatch(
                championship=championship,
                kickoff_unix=dt.timestamp(),
                home_team=home,
                away_team=away,
                home_goals=int(hg),
                away_goals=int(ag),
            )
        )

    out.sort(key=lambda m: m.kickoff_unix)
    return out


def load_calendar_fixtures(
    *,
    base_dir: Path,
    calendar_filename: str,
    championship: str,
    now_utc: datetime,
) -> list[LocalFixture]:
    pd = _pd()
    p = local_calendar_path(base_dir=base_dir, calendar_filename=calendar_filename)
    if not p.exists():
        return []

    sheet = _CALENDAR_SHEETS.get(championship)
    if not sheet:
        raise ValueError("unsupported_championship")

    df = pd.read_excel(p, sheet_name=sheet)
    required = {"Giornata", "Data", "Casa", "Risultato", "Trasferta"}
    if not required.issubset(set(df.columns)):
        return []

    out: list[LocalFixture] = []
    today = now_utc.date()
    for i, r in df.iterrows():
        home = str(r.get("Casa") or "").strip()
        away = str(r.get("Trasferta") or "").strip()
        if not home or not away:
            continue

        md = _parse_matchday(str(r.get("Giornata") or ""))
        d = _parse_date_only(r.get("Data"))
        if d is None:
            continue

        res = str(r.get("Risultato") or "").strip()
        kickoff_t = _parse_kickoff_time(res, date_is_future=(d >= today))
        if kickoff_t is None:
            kickoff_t = time(15, 0)

        kickoff_dt = datetime(d.year, d.month, d.day, kickoff_t.hour, kickoff_t.minute, tzinfo=timezone.utc)
        status = "PREMATCH"
        final_score = None
        if d < today:
            score = _parse_score(res)
            if score is not None:
                status = "FINISHED"
                final_score = score

        out.append(
            LocalFixture(
                championship=championship,
                matchday=md,
                kickoff_unix=kickoff_dt.timestamp(),
                home_team=home,
                away_team=away,
                status=status,
                final_score=final_score,
                source={"provider": "local_files", "file": str(p), "sheet": sheet, "row": int(i)},
            )
        )

    out.sort(key=lambda x: (x.kickoff_unix or 0.0, x.matchday is None, x.matchday or 0))
    return out


def _pd() -> Any:
    try:
        import pandas as pd  # type: ignore

        return pd
    except Exception as e:
        raise RuntimeError("pandas_required_for_local_files") from e


def _find_header_row(df: Any) -> int | None:
    try:
        n = int(getattr(df, "shape")[0])
    except Exception:
        return None
    for i in range(min(15, n)):
        row = df.iloc[i].tolist()
        cells = {str(x).strip() for x in row if isinstance(x, str) and x.strip()}
        if {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}.issubset(cells) and (("Date" in cells) or ("MatchDate" in cells)):
            return i
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


def _parse_date_only(v: Any) -> datetime.date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str) and v.strip():
        s = v.strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
        try:
            dt = datetime.fromisoformat(s)
            return dt.date()
        except Exception:
            return None
    return None


def _parse_datetime(*, date_val: Any, time_val: Any) -> datetime | None:
    d = None
    if isinstance(date_val, datetime):
        d = date_val.date()
    elif isinstance(date_val, str) and date_val.strip():
        try:
            d = datetime.strptime(date_val.strip(), "%Y-%m-%d").date()
        except Exception:
            try:
                d = datetime.fromisoformat(date_val.strip()).date()
            except Exception:
                d = None
    if d is None:
        return None

    t = time(12, 0)
    if isinstance(time_val, datetime):
        t = time_val.time()
    elif isinstance(time_val, str) and time_val.strip():
        s = time_val.strip()
        try:
            t = datetime.strptime(s, "%H:%M").time()
        except Exception:
            t = time(12, 0)

    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=timezone.utc)


def _parse_matchday(s: str) -> int | None:
    digits: list[str] = []
    cur: list[str] = []
    for ch in str(s or ""):
        if ch.isdigit():
            cur.append(ch)
        else:
            if cur:
                digits.append("".join(cur))
                cur.clear()
    if cur:
        digits.append("".join(cur))
    if not digits:
        return None
    try:
        return int(digits[-1])
    except Exception:
        return None


def _parse_score(s: str) -> dict[str, int] | None:
    parts = str(s or "").strip().split(":")
    if len(parts) != 2:
        return None
    a, b = parts[0].strip(), parts[1].strip()
    if not a.isdigit() or not b.isdigit():
        return None
    ha, aa = int(a), int(b)
    if ha < 0 or aa < 0 or ha > 20 or aa > 20:
        return None
    return {"home": ha, "away": aa}


def _parse_kickoff_time(s: str, *, date_is_future: bool) -> time | None:
    if not date_is_future:
        return None
    parts = str(s or "").strip().split(":")
    if len(parts) != 2:
        return None
    a, b = parts[0].strip(), parts[1].strip()
    if not a.isdigit() or not b.isdigit():
        return None
    hh, mm = int(a), int(b)
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    if mm not in {0, 15, 30, 45}:
        return None
    if hh < 10 and len(a) < 2:
        return None
    return time(hh, mm)
