from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SetPieceLookup:
    off_index: float
    def_index: float
    meta: dict[str, Any]


_CACHE: dict[str, Any] = {"path": None, "mtime": None, "payload": None}


def _norm_team_name(s: str) -> str:
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    for ch in ["’", "'", ".", ",", "-", "_"]:
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    return s


def _load_payload(path: str) -> dict[str, Any] | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        mtime = p.stat().st_mtime
        if _CACHE["path"] == str(p) and _CACHE["mtime"] == mtime and isinstance(_CACHE["payload"], dict):
            return _CACHE["payload"]
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            _CACHE.update({"path": str(p), "mtime": mtime, "payload": payload})
            return payload
    except Exception:
        return None
    return None


def get_team_setpieces(*, championship: str, team: str, path: str | None = None) -> SetPieceLookup | None:
    idx_path = path or os.getenv("SETPIECE_INDEX_PATH") or "data/team_setpiece_index.json"
    payload = _load_payload(idx_path)
    if not isinstance(payload, dict):
        return None

    champs = payload.get("championships")
    if not isinstance(champs, dict):
        return None

    champ = champs.get(str(championship))
    if not isinstance(champ, dict):
        return None

    teams = champ.get("teams")
    if not isinstance(teams, dict):
        return None

    t_exact = teams.get(team)
    if isinstance(t_exact, dict):
        try:
            return SetPieceLookup(
                off_index=float(t_exact.get("off_index", 0.0) or 0.0),
                def_index=float(t_exact.get("def_index", 0.0) or 0.0),
                meta=dict(champ.get("meta", {}) or {}),
            )
        except Exception:
            return None

    want = _norm_team_name(team)
    for k, v in teams.items():
        if _norm_team_name(k) == want and isinstance(v, dict):
            try:
                return SetPieceLookup(
                    off_index=float(v.get("off_index", 0.0) or 0.0),
                    def_index=float(v.get("def_index", 0.0) or 0.0),
                    meta=dict(champ.get("meta", {}) or {}),
                )
            except Exception:
                return None

    return None


def get_team_setpiece(*, championship: str, team: str, setpiece_path: str | None = None) -> SetPieceLookup | None:
    return get_team_setpieces(championship=championship, team=team, path=setpiece_path)
