from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RatingsLookup:
    strength: float
    meta: dict[str, Any]


_CACHE: dict[str, Any] = {"path": None, "mtime_ns": None, "data": None}


def _default_ratings_path() -> str:
    return os.getenv("FORECAST_RATINGS_PATH", "data/team_ratings.json")


def _load_ratings(path: str) -> dict[str, Any] | None:
    p = Path(path)
    try:
        st = p.stat()
    except Exception:
        _CACHE.update({"path": str(p), "mtime_ns": None, "data": None})
        return None

    if _CACHE.get("path") == str(p) and _CACHE.get("mtime_ns") == st.st_mtime_ns and isinstance(_CACHE.get("data"), dict):
        return _CACHE["data"]

    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        _CACHE.update({"path": str(p), "mtime_ns": st.st_mtime_ns, "data": None})
        return None

    if not isinstance(data, dict):
        _CACHE.update({"path": str(p), "mtime_ns": st.st_mtime_ns, "data": None})
        return None

    norm_index: dict[str, dict[str, str]] = {}
    champs = data.get("championships")
    if isinstance(champs, dict):
        for champ, champ_row in champs.items():
            if not isinstance(champ_row, dict):
                continue
            teams = champ_row.get("teams")
            if not isinstance(teams, dict):
                continue
            idx: dict[str, str] = {}
            for name in teams.keys():
                if not isinstance(name, str):
                    continue
                n = _normalize_team_name(name)
                if n and n not in idx:
                    idx[n] = name
            norm_index[str(champ)] = idx

    _CACHE.update({"path": str(p), "mtime_ns": st.st_mtime_ns, "data": data, "norm_index": norm_index})
    return data


def _normalize_team_name(s: str) -> str:
    v0 = str(s or "").lower()
    v = "".join(ch for ch in unicodedata.normalize("NFKD", v0) if not unicodedata.combining(ch))
    for ch in ("’", "'", ".", ",", "(", ")", "[", "]", "-", "_", "/", "\\"):
        v = v.replace(ch, " ")
    parts = [p for p in v.split() if p]
    drop = {
        "fc",
        "cfc",
        "afc",
        "cf",
        "ac",
        "as",
        "us",
        "ssc",
        "ss",
        "calcio",
        "club",
        "sporting",
        "bk",
        "fk",
        "il",
        "sk",
        "ff",
        "if",
        "tsv",
        "sv",
        "vfb",
        "vfl",
        "bv",
        "borussia",
        "rb",
        "hellas",
    }
    kept = [p for p in parts if p not in drop]
    if not kept:
        kept = parts
    out = "".join(ch for ch in "".join(kept) if ch.isalpha())
    return out


def get_team_strength(*, championship: str, team: str, ratings_path: str | None = None) -> RatingsLookup | None:
    path = ratings_path or _default_ratings_path()
    data = _load_ratings(path)
    if not isinstance(data, dict):
        return None

    champs = data.get("championships")
    if not isinstance(champs, dict):
        return None

    champ_row = champs.get(championship)
    if not isinstance(champ_row, dict):
        return None

    teams = champ_row.get("teams")
    if not isinstance(teams, dict):
        return None

    key = str(team or "").strip()
    row = teams.get(key)
    if not isinstance(row, dict):
        n = _normalize_team_name(key)
        idx = _CACHE.get("norm_index")
        if isinstance(idx, dict):
            champ_idx = idx.get(str(championship))
            if isinstance(champ_idx, dict) and isinstance(n, str) and n:
                mapped = champ_idx.get(n)
                if isinstance(mapped, str):
                    row = teams.get(mapped)
                if not isinstance(row, dict):
                    best_mapped: str | None = None
                    best_len = 0
                    for cand_norm, original_name in champ_idx.items():
                        if not isinstance(cand_norm, str) or not isinstance(original_name, str):
                            continue
                        if not cand_norm:
                            continue
                        if cand_norm in n or n in cand_norm:
                            overlap = min(len(cand_norm), len(n))
                            if overlap >= 5 and overlap > best_len:
                                best_len = overlap
                                best_mapped = original_name
                    if isinstance(best_mapped, str):
                        row = teams.get(best_mapped)
    if not isinstance(row, dict):
        return None

    strength = row.get("strength")
    if not isinstance(strength, (int, float)):
        return None

    meta: dict[str, Any] = {
        "ratings_generated_at_utc": data.get("generated_at_utc"),
        "ratings_asof_utc": data.get("asof_utc"),
        "ratings_source": "elo",
        "ratings_path": path,
    }
    return RatingsLookup(strength=float(strength), meta=meta)
