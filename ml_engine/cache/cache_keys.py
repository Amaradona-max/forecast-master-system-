from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def stable_json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_hex(raw)


def build_cache_key(
    *,
    championship: str,
    match_id: str,
    model_version: str,
    feature_version: str,
    calibrator_version: str,
    inputs_hash: str,
) -> str:
    key = f"{championship}|{match_id}|{model_version}|{feature_version}|{calibrator_version}|{inputs_hash}"
    return sha256_hex(key)

