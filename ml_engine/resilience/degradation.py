from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Degradation:
    level: int
    warnings: list[str]


def build_degradation(*, cache_disabled: bool, calibration_disabled: bool, deadline_low: bool) -> Degradation:
    level = 0
    warnings: list[str] = []
    if cache_disabled:
        level = max(level, 1)
        warnings.append("cache_disabled")
    if calibration_disabled:
        level = max(level, 2)
        warnings.append("calibration_disabled")
    if deadline_low:
        level = max(level, 1)
        warnings.append("deadline_low")
    return Degradation(level=level, warnings=warnings)

