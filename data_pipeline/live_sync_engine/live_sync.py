from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LiveMatchUpdate:
    match_id: str
    payload: dict[str, Any]
    received_at_unix: float


class LiveSyncEngine:
    def __init__(self) -> None:
        self._buffer: list[LiveMatchUpdate] = []

    def push(self, match_id: str, payload: dict[str, Any]) -> None:
        self._buffer.append(LiveMatchUpdate(match_id=match_id, payload=dict(payload), received_at_unix=time.time()))

    def drain(self) -> list[LiveMatchUpdate]:
        items = list(self._buffer)
        self._buffer.clear()
        return items

