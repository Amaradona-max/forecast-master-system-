from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

_STOPWORDS = {
    "fc",
    "ac",
    "cf",
    "sc",
    "ssc",
    "afc",
    "the",
    "calcio",
    "football",
    "club",
    "futbol",
    "de",
    "del",
    "della",
    "la",
    "el",
    "sporting",
    "atletico",
    "athletic",
}

_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def _strip_accents(s: str) -> str:
    nkfd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nkfd if not unicodedata.combining(ch))


def canonicalize(name: str) -> str:
    s = (name or "").strip().lower()
    s = _strip_accents(s)
    s = s.replace("&", " and ")
    s = s.replace("-", " ")
    s = _NON_ALNUM_RE.sub(" ", s)
    parts = [p for p in _SPACE_RE.split(s) if p and p not in _STOPWORDS]
    return " ".join(parts).strip()


@dataclass(frozen=True)
class ResolveResult:
    raw: str
    canonical: str
    resolved: str
    method: str  # exact|alias|fuzzy|none
    score: float


class TeamNameResolver:
    """
    Risolve nomi in modo stabile con:
    - canonicalize()
    - alias per campionato (file json)
    - fuzzy fallback (difflib) SOLO se serve

    Note:
    - alias file può contenere sia "raw->canonical target" sia "canonical->canonical".
    - target deve essere il nome "ufficiale" usato internamente (es: per team_form.json / ratings / modellistica).
    """

    def __init__(
        self,
        *,
        aliases_path: str,
        enable_fuzzy: bool = True,
        fuzzy_cutoff: float = 0.86,
    ) -> None:
        self.aliases_path = str(aliases_path)
        self.enable_fuzzy = bool(enable_fuzzy)
        self.fuzzy_cutoff = float(fuzzy_cutoff)
        self._data: dict[str, Any] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            p = Path(self.aliases_path)
            if not p.exists():
                self._data = {}
                return
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._data = data if isinstance(data, dict) else {}
        except Exception:
            self._data = {}

    def _champ_aliases(self, championship: str) -> dict[str, str]:
        self._load()
        champs = self._data.get("championships")
        if not isinstance(champs, dict):
            return {}
        row = champs.get(str(championship))
        if not isinstance(row, dict):
            return {}
        aliases = row.get("aliases")
        return aliases if isinstance(aliases, dict) else {}

    def _champ_vocab(self, championship: str) -> list[str]:
        self._load()
        champs = self._data.get("championships")
        if not isinstance(champs, dict):
            return []
        row = champs.get(str(championship))
        if not isinstance(row, dict):
            return []
        vocab = row.get("vocab")
        if isinstance(vocab, list):
            return [str(x) for x in vocab if str(x).strip()]
        return []

    def resolve(self, *, championship: str, name: str) -> ResolveResult:
        raw = str(name or "")
        can = canonicalize(raw)
        if not can:
            return ResolveResult(raw=raw, canonical="", resolved=raw, method="none", score=0.0)

        aliases = self._champ_aliases(championship)
        if raw in aliases:
            return ResolveResult(raw=raw, canonical=can, resolved=str(aliases[raw]), method="alias", score=1.0)
        if can in aliases:
            return ResolveResult(raw=raw, canonical=can, resolved=str(aliases[can]), method="alias", score=1.0)

        vocab = self._champ_vocab(championship)
        if vocab:
            can_map = {canonicalize(v): v for v in vocab}
            if can in can_map:
                return ResolveResult(raw=raw, canonical=can, resolved=str(can_map[can]), method="exact", score=1.0)

            if self.enable_fuzzy:
                cands = list(can_map.keys())
                best = get_close_matches(can, cands, n=1, cutoff=self.fuzzy_cutoff)
                if best:
                    resolved = can_map[best[0]]
                    return ResolveResult(raw=raw, canonical=can, resolved=str(resolved), method="fuzzy", score=0.9)

        return ResolveResult(raw=raw, canonical=can, resolved=raw, method="none", score=0.0)

