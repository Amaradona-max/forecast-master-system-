from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket


@dataclass
class LiveUpdateEvent:
    type: str
    payload: dict[str, Any]


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: LiveUpdateEvent) -> None:
        msg = json.dumps({"type": event.type, "payload": event.payload}, ensure_ascii=False)
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(msg)
            except Exception:
                await self.disconnect(ws)

    async def iter_events(self, ws: WebSocket) -> AsyncIterator[dict[str, Any]]:
        while True:
            data = await ws.receive_json()
            if isinstance(data, dict):
                yield data

