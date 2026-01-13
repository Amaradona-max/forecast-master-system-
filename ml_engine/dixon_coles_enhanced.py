from __future__ import annotations

import math
from typing import Any


def dc_correction(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - (lam * mu * rho)
    if x == 0 and y == 1:
        return 1.0 + (lam * rho)
    if x == 1 and y == 0:
        return 1.0 + (mu * rho)
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def dixon_coles_1x2(*, lam_home: float, lam_away: float, rho: float = 0.08, max_goals: int = 10) -> dict[str, Any]:
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0

    for x in range(max_goals + 1):
        px = poisson_pmf(x, lam_home)
        for y in range(max_goals + 1):
            py = poisson_pmf(y, lam_away)
            tau = dc_correction(x, y, lam_home, lam_away, rho)
            p = tau * px * py
            if x > y:
                p_home += p
            elif x == y:
                p_draw += p
            else:
                p_away += p

    s = p_home + p_draw + p_away
    if s <= 0:
        return {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
    return {"home_win": p_home / s, "draw": p_draw / s, "away_win": p_away / s}

