from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class HistoricalIngestor:
    def __init__(self, *, base_dir: Path) -> None:
        self._base_dir = base_dir

    def load_jsonl(self, relative_path: str) -> list[dict[str, Any]]:
        p = (self._base_dir / relative_path).resolve()
        if not p.exists():
            return []
        out: list[dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
        return out

