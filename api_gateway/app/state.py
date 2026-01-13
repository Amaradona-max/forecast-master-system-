from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveMatchState:
    match_id: str
    championship: str
    home_team: str
    away_team: str
    status: str = "PREMATCH"
    matchday: int | None = None
    kickoff_unix: float | None = None
    next_update_unix: float | None = None
    updated_at_unix: float = field(default_factory=lambda: time.time())
    probabilities: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def update(
        self,
        *,
        status: str | None = None,
        matchday: int | None = None,
        kickoff_unix: float | None = None,
        next_update_unix: float | None = None,
        probabilities: dict[str, float] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if status is not None:
            self.status = status
        if matchday is not None:
            self.matchday = matchday
        if kickoff_unix is not None:
            self.kickoff_unix = kickoff_unix
        if next_update_unix is not None:
            self.next_update_unix = next_update_unix
        if probabilities is not None:
            self.probabilities = probabilities
        if meta is not None:
            self.meta = meta
        self.updated_at_unix = time.time()


class AppState:
    def __init__(self) -> None:
        self.matches: dict[str, LiveMatchState] = {}
        self._lock = asyncio.Lock()

    async def upsert_match(self, match: LiveMatchState) -> None:
        async with self._lock:
            self.matches[match.match_id] = match

    async def get_match(self, match_id: str) -> LiveMatchState | None:
        async with self._lock:
            return self.matches.get(match_id)

    async def list_matches(self) -> list[LiveMatchState]:
        async with self._lock:
            return list(self.matches.values())
