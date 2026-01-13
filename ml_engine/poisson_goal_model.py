from __future__ import annotations

import math
from typing import Any


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def match_probabilities(*, lam_home: float, lam_away: float, max_goals: int = 10) -> dict[str, Any]:
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    p_over_25 = 0.0
    p_btts = 0.0

    for x in range(max_goals + 1):
        px = poisson_pmf(x, lam_home)
        for y in range(max_goals + 1):
            py = poisson_pmf(y, lam_away)
            p = px * py
            if x > y:
                p_home += p
            elif x == y:
                p_draw += p
            else:
                p_away += p
            if (x + y) >= 3:
                p_over_25 += p
            if x >= 1 and y >= 1:
                p_btts += p

    s = p_home + p_draw + p_away
    if s <= 0:
        probs_1x2 = {"home_win": 1 / 3, "draw": 1 / 3, "away_win": 1 / 3}
    else:
        probs_1x2 = {"home_win": p_home / s, "draw": p_draw / s, "away_win": p_away / s}

    return {
        "1x2": probs_1x2,
        "goals": {
            "lam_home": float(lam_home),
            "lam_away": float(lam_away),
            "over_2_5": float(min(max(p_over_25, 0.0), 1.0)),
            "btts": float(min(max(p_btts, 0.0), 1.0)),
        },
    }

