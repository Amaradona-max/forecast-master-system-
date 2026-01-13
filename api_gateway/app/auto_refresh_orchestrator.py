from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from api_gateway.app.state import LiveMatchState


@dataclass(frozen=True)
class UpdateFrequencies:
    prematch_schedule_seconds: tuple[int, ...] = (24 * 3600, 12 * 3600, 6 * 3600, 3600)
    in_match_seconds: int = 30
    post_match_seconds: tuple[int, ...] = (0, 3600)


class AutoRefreshOrchestrator:
    def __init__(self, frequencies: UpdateFrequencies | None = None) -> None:
        self._freq = frequencies or UpdateFrequencies()

    def compute_next_update_unix(self, match: LiveMatchState, *, now_unix: float | None = None) -> float:
        now = float(now_unix if now_unix is not None else time.time())

        if match.status == "LIVE":
            return now + self._freq.in_match_seconds

        if match.status == "FINISHED":
            last = match.meta.get("_post_match_updates", 0)
            if not isinstance(last, int):
                last = 0
            if last <= 0:
                return now
            return now + self._freq.post_match_seconds[1]

        kickoff = match.kickoff_unix
        if kickoff is None:
            return now + 3600

        delta = kickoff - now
        if delta <= 0:
            return now + 60

        nearest = min(self._freq.prematch_schedule_seconds, key=lambda t: abs(delta - t))
        return now + max(60, min(int(nearest / 12), 15 * 60))

    def smart_update_context(self, match: LiveMatchState, *, now_unix: float | None = None) -> dict[str, Any]:
        now = float(now_unix if now_unix is not None else time.time())
        kickoff = match.kickoff_unix or (now + 3600)
        minutes_to_kickoff = int((kickoff - now) / 60)

        if match.status == "PREMATCH":
            has_lineups = minutes_to_kickoff <= 60
            return {"lineups": "official" if has_lineups else "tbd"}

        if match.status == "LIVE":
            return {"events": match.meta.get("context", {}).get("events", [])}

        return {"retrain": True}

