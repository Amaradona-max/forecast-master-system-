from __future__ import annotations

from typing import Any, Dict, List


def _human_feature(f: str) -> str:
    f = str(f)
    m = {
        "rest_diff": "giorni di riposo",
        "home_days_rest": "riposo casa",
        "away_days_rest": "riposo trasferta",
        "home_pts_last5": "forma recente casa",
        "away_pts_last5": "forma recente trasferta",
        "home_gf_last5": "gol segnati casa (ultime 5)",
        "away_gf_last5": "gol segnati trasferta (ultime 5)",
        "home_ga_last5": "gol subiti casa (ultime 5)",
        "away_ga_last5": "gol subiti trasferta (ultime 5)",
        "home_adv": "vantaggio casa",
        "strength_diff": "differenza forza",
    }
    if f in m:
        return m[f]
    return f.replace("home_", "casa ").replace("away_", "trasferta ").replace("_", " ")


def summarize_match_compare(compare: Dict[str, Any], *, max_factors: int = 3) -> str | None:
    if not isinstance(compare, dict):
        return None
    drivers = compare.get("drivers")
    if not isinstance(drivers, list) or not drivers:
        return None

    top = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        feat = d.get("feature")
        imp = d.get("impact_pct")
        win = d.get("winner")
        if feat is None or imp is None or win not in ("A", "B"):
            continue
        try:
            imp = float(imp)
        except Exception:
            continue
        top.append((str(feat), imp, str(win)))

    if not top:
        return None

    top.sort(key=lambda x: x[1], reverse=True)
    top = top[:max_factors]

    pro_a = [_human_feature(f) for f, _, w in top if w == "A"]
    pro_b = [_human_feature(f) for f, _, w in top if w == "B"]

    def _join(xs: List[str]) -> str:
        if not xs:
            return ""
        if len(xs) == 1:
            return xs[0]
        if len(xs) == 2:
            return f"{xs[0]} e {xs[1]}"
        return f"{', '.join(xs[:-1])} e {xs[-1]}"

    a_txt = _join(pro_a)
    b_txt = _join(pro_b)

    if a_txt and b_txt:
        return f"Match A è preferibile perché {a_txt} pesa di più, mentre nel Match B incidono soprattutto {b_txt}."
    if a_txt:
        return f"Match A è preferibile soprattutto grazie a {a_txt}."
    if b_txt:
        return f"Match B risulta migliore perché {b_txt} fa la differenza."
    return None
