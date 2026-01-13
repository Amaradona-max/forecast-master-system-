from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ChampionshipDataset:
    championship: str
    season_start: date
    season_end: date
    matches: list[dict[str, Any]] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)

    def upsert_match(self, match: dict[str, Any]) -> None:
        match_id = str(match.get("match_id", "")).strip()
        if not match_id:
            raise ValueError("match_id_required")
        for i, m in enumerate(self.matches):
            if str(m.get("match_id")) == match_id:
                self.matches[i] = match
                return
        self.matches.append(match)

    def upsert_features(self, match_id: str, feats: dict[str, Any]) -> None:
        match_id = str(match_id).strip()
        if not match_id:
            raise ValueError("match_id_required")
        row = dict(feats)
        row["match_id"] = match_id
        for i, f in enumerate(self.features):
            if str(f.get("match_id")) == match_id:
                self.features[i] = row
                return
        self.features.append(row)

