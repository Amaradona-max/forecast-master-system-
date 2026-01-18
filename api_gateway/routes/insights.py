from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api_gateway.app.settings import settings
from api_gateway.app.state import AppState


router = APIRouter()

def _tenant_id_from_request(request: Request) -> str:
    tid = request.headers.get("x-tenant-id")
    if isinstance(tid, str) and tid.strip():
        return tid.strip().lower()
    qp = request.query_params.get("tenant") or request.query_params.get("tenant_id")
    if isinstance(qp, str) and qp.strip():
        return qp.strip().lower()
    return "default"


def _country_from_request(request: Request) -> str | None:
    for k in ("cf-ipcountry", "x-country", "x-geo-country"):
        v = request.headers.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return None


def _apply_region_policy(request: Request, compliance: dict[str, Any]) -> None:
    if not isinstance(compliance, dict):
        return
    cc = _country_from_request(request)
    allow = compliance.get("allowed_countries")
    block = compliance.get("blocked_countries")
    allow_list = [str(x).strip().upper() for x in (allow if isinstance(allow, list) else []) if str(x).strip()]
    block_list = [str(x).strip().upper() for x in (block if isinstance(block, list) else []) if str(x).strip()]
    if cc is None:
        return
    if block_list and cc in set(block_list):
        raise HTTPException(status_code=451, detail="region_blocked")
    if allow_list and cc not in set(allow_list):
        raise HTTPException(status_code=451, detail="region_not_allowed")


def _confidence_label_from_pct(v: Any) -> str:
    try:
        n = int(v)
    except Exception:
        n = 0
    if n >= 75:
        return "HIGH"
    if n >= 55:
        return "MEDIUM"
    return "LOW"


def _min_conf_ok(*, confidence_pct: int, min_label: str) -> bool:
    cur = _confidence_label_from_pct(confidence_pct)
    want = str(min_label or "").strip().upper() or "LOW"
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return rank.get(cur, 0) >= rank.get(want, 0)



class TeamToPlay(BaseModel):
    team: str
    success_pct: float
    form_pct: float


class TeamsToPlayItem(BaseModel):
    championship: str
    top3: list[TeamToPlay] = Field(default_factory=list)


class TeamsToPlayResponse(BaseModel):
    generated_at_utc: datetime
    items: list[TeamsToPlayItem] = Field(default_factory=list)


class StakeSuggestionResponse(BaseModel):
    stake_pct: float
    stake_units: int
    bankroll_reference: float


class MarketConfidence(BaseModel):
    probability: float
    confidence: int
    risk: str


class MultiMarketConfidenceResponse(BaseModel):
    generated_at_utc: datetime
    match_id: str
    match: str
    markets: dict[str, MarketConfidence] = Field(default_factory=dict)


def _championship_display_name(championship: str) -> str:
    c = str(championship or "").strip().lower()
    mapping = {
        "serie_a": "Serie A",
        "premier_league": "Premier League",
        "la_liga": "La Liga",
        "bundesliga": "Bundesliga",
        "eliteserien": "Eliteserien",
    }
    return mapping.get(c, str(championship))


def _clamp01(x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return float(x)


def _strength_to_pct(strength: float) -> float:
    s = float(strength)
    if s < -0.9:
        s = -0.9
    if s > 0.9:
        s = 0.9
    return _clamp01((s + 0.9) / 1.8)


def _norm_confidence_label(v: Any) -> str:
    s = str(v or "").strip().upper()
    if s in {"HIGH", "ALTA", "A"}:
        return "HIGH"
    if s in {"MEDIUM", "MEDIA", "M"}:
        return "MEDIUM"
    return "LOW"


def _norm_risk(v: Any) -> str:
    s = str(v or "").strip().upper()
    if s in {"LOW", "BASSO", "BASSA", "L"}:
        return "LOW"
    return "MEDIUM"


def _stake_pct_for(*, confidence_label: str, risk: str) -> float:
    c = _norm_confidence_label(confidence_label)
    r = _norm_risk(risk)
    if c == "LOW":
        return 1.0
    if c == "HIGH" and r == "LOW":
        return 4.5
    if c == "HIGH" and r == "MEDIUM":
        return 3.0
    if c == "MEDIUM" and r == "LOW":
        return 2.0
    return 1.25


@router.get("/api/v1/stake/suggest", response_model=StakeSuggestionResponse)
async def stake_suggest(request: Request, confidence: str, risk: str = "LOW", bankroll_reference: float = 100.0) -> StakeSuggestionResponse:
    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    if bool(compliance.get("educational_only", False)):
        raise HTTPException(status_code=403, detail="educational_only")
    try:
        br = float(bankroll_reference)
    except Exception:
        br = 100.0
    if br < 0.0:
        br = 0.0
    if br > 1_000_000.0:
        br = 1_000_000.0
    pct = float(_stake_pct_for(confidence_label=confidence, risk=risk))
    units = int(round(br * pct / 100.0)) if br > 0.0 else 0
    if units < 0:
        units = 0
    return StakeSuggestionResponse(stake_pct=round(pct, 2), stake_units=int(units), bankroll_reference=float(br))


def _confidence_pct_from_score(score: Any) -> int:
    try:
        s = float(score)
    except Exception:
        s = 0.0
    if s < 0.0:
        s = 0.0
    if s > 1.0:
        s = 1.0
    return int(round(s * 100.0))


def _quality_from_explain(explain: dict[str, Any]) -> float:
    safe_mode = bool(explain.get("safe_mode"))
    missing = explain.get("missing_flags")
    missing_count = len(missing) if isinstance(missing, list) else 0
    q = 1.0
    if missing_count >= 2:
        q *= 0.70
    elif missing_count == 1:
        q *= 0.85
    if safe_mode:
        q *= 0.85
    if q < 0.10:
        q = 0.10
    if q > 1.0:
        q = 1.0
    return float(q)


def _binary_confidence(prob: float, quality: float) -> int:
    try:
        p = float(prob)
    except Exception:
        p = 0.0
    if p < 0.0:
        p = 0.0
    if p > 1.0:
        p = 1.0
    strength = abs(p - 0.5) * 2.0
    s = strength * float(quality)
    if s < 0.0:
        s = 0.0
    if s > 1.0:
        s = 1.0
    return int(round(s * 100.0))


def _risk_from_confidence(confidence: int, quality: float) -> str:
    c = int(confidence)
    if c < 45:
        return "HIGH"
    if c >= 75 and float(quality) >= 0.90:
        return "LOW"
    return "MEDIUM"


@router.get("/api/v1/insights/multi-market", response_model=MultiMarketConfidenceResponse)
async def multi_market_confidence(request: Request, match_id: str) -> MultiMarketConfidenceResponse:
    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    m = await state.get_match(str(match_id))
    if m is None:
        return MultiMarketConfidenceResponse(generated_at_utc=datetime.now(timezone.utc), match_id=str(match_id), match="", markets={})

    explain0: dict[str, Any] = {}
    if isinstance(getattr(m, "meta", None), dict):
        x = m.meta.get("explain")
        if isinstance(x, dict):
            explain0 = x

    quality = _quality_from_explain(explain0)
    probs0 = getattr(m, "probabilities", None)
    probs = probs0 if isinstance(probs0, dict) else {}
    p1 = float(probs.get("home_win", 0.0) or 0.0)
    px = float(probs.get("draw", 0.0) or 0.0)
    p2 = float(probs.get("away_win", 0.0) or 0.0)
    s = max(p1, 0.0) + max(px, 0.0) + max(p2, 0.0)
    if s > 0:
        p1, px, p2 = max(p1, 0.0) / s, max(px, 0.0) / s, max(p2, 0.0) / s
    else:
        p1, px, p2 = 1 / 3, 1 / 3, 1 / 3
    top_prob = max(p1, px, p2)

    conf_obj = explain0.get("confidence")
    conf_score = None
    if isinstance(conf_obj, dict):
        v = conf_obj.get("score")
        if isinstance(v, (int, float)):
            conf_score = float(v)
    conf_1x2 = _confidence_pct_from_score(conf_score if conf_score is not None else (top_prob * quality))
    risk_1x2 = _risk_from_confidence(conf_1x2, quality)

    derived = explain0.get("derived_markets")
    dmk = derived if isinstance(derived, dict) else {}
    p_over25 = float(dmk.get("over_2_5", 0.0) or 0.0)
    p_btts = float(dmk.get("btts", 0.0) or 0.0)

    conf_over25 = _binary_confidence(p_over25, quality)
    conf_btts = _binary_confidence(p_btts, quality)
    risk_over25 = _risk_from_confidence(conf_over25, quality)
    risk_btts = _risk_from_confidence(conf_btts, quality)

    match_label = f"{str(getattr(m, 'home_team', '') or '').strip()} vs {str(getattr(m, 'away_team', '') or '').strip()}".strip()
    markets = {
        "1X2": MarketConfidence(probability=float(top_prob), confidence=int(conf_1x2), risk=str(risk_1x2)),
        "OVER_2_5": MarketConfidence(probability=float(_clamp01(p_over25)), confidence=int(conf_over25), risk=str(risk_over25)),
        "BTTS": MarketConfidence(probability=float(_clamp01(p_btts)), confidence=int(conf_btts), risk=str(risk_btts)),
    }
    filters = tenant_cfg.get("filters") if isinstance(tenant_cfg.get("filters"), dict) else {}
    allowed_markets_raw = filters.get("active_markets")
    allowed_markets = [str(x).strip().upper() for x in (allowed_markets_raw if isinstance(allowed_markets_raw, list) else []) if str(x).strip()]
    if allowed_markets:
        allow_set = set(allowed_markets)
        markets = {k: v for k, v in markets.items() if str(k).upper() in allow_set}
    min_label = str(filters.get("min_confidence") or "LOW").strip().upper() or "LOW"
    markets = {k: v for k, v in markets.items() if _min_conf_ok(confidence_pct=int(v.confidence), min_label=min_label)}
    return MultiMarketConfidenceResponse(
        generated_at_utc=datetime.now(timezone.utc),
        match_id=str(match_id),
        match=match_label,
        markets=markets,
    )


def _read_ratings() -> dict[str, dict[str, float]]:
    p = Path(str(settings.ratings_path or "data/team_ratings.json"))
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    champs = raw.get("championships") if isinstance(raw, dict) else None
    if not isinstance(champs, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for champ, row in champs.items():
        if not isinstance(row, dict):
            continue
        teams = row.get("teams")
        if not isinstance(teams, dict):
            continue
        strengths: dict[str, float] = {}
        for team, trow in teams.items():
            if not isinstance(team, str) or not isinstance(trow, dict):
                continue
            s = trow.get("strength")
            if isinstance(s, (int, float)):
                strengths[team] = float(s)
        if strengths:
            out[str(champ)] = strengths
    return out


def _extract_final_score(meta: Any) -> tuple[int, int] | None:
    if not isinstance(meta, dict):
        return None
    ctx = meta.get("context") if isinstance(meta.get("context"), dict) else None
    if not isinstance(ctx, dict):
        return None
    fs = ctx.get("final_score")
    if not isinstance(fs, dict):
        return None
    hg = fs.get("home")
    ag = fs.get("away")
    if not isinstance(hg, int) or not isinstance(ag, int):
        return None
    return (int(hg), int(ag))


class ExplainTeamStrength(BaseModel):
    team: str
    strength_pct: float | None = None
    strength_vs_avg_pp: float | None = None


class ExplainForm(BaseModel):
    last_n: int
    w: int
    d: int
    l: int


class ExplainContext(BaseModel):
    home: bool | None = None
    opponent_team: str | None = None
    h2h_last_n: int | None = None
    h2h_w: int | None = None
    h2h_d: int | None = None
    h2h_l: int | None = None


class ExplainResponse(BaseModel):
    generated_at_utc: datetime
    championship: str
    match_id: str | None = None
    team: str
    pick: str | None = None
    why: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    strength: ExplainTeamStrength | None = None
    form: ExplainForm | None = None
    context: ExplainContext | None = None


def _norm_team(name: Any) -> str:
    s = str(name or "").strip()
    s = " ".join(s.split())
    if len(s) > 80:
        s = s[:80]
    return s


def _strength_stats_for_team(ratings: dict[str, dict[str, float]], championship: str, team: str) -> tuple[float | None, float | None]:
    champ = str(championship or "").strip()
    t = _norm_team(team)
    strengths = ratings.get(champ)
    if not isinstance(strengths, dict) or not strengths:
        return (None, None)
    vals = [float(_strength_to_pct(v)) * 100.0 for v in strengths.values() if isinstance(v, (int, float))]
    if not vals:
        return (None, None)
    avg = sum(vals) / float(len(vals))
    s_raw = strengths.get(t)
    if not isinstance(s_raw, (int, float)):
        return (None, None)
    pct = float(_strength_to_pct(float(s_raw))) * 100.0
    return (round(pct, 1), round(pct - avg, 1))


def _form_for_team(matches: list[Any], championship: str, team: str, n: int) -> tuple[int, int, int]:
    champ = str(championship or "").strip()
    t = _norm_team(team)
    games: list[tuple[float, str, str, int, int]] = []
    for m in matches:
        if str(getattr(m, "championship", "") or "").strip() != champ:
            continue
        if str(getattr(m, "status", "") or "").upper() != "FINISHED":
            continue
        if getattr(m, "kickoff_unix", None) is None:
            continue
        fs = _extract_final_score(getattr(m, "meta", None))
        if fs is None:
            continue
        games.append((float(m.kickoff_unix), _norm_team(getattr(m, "home_team", "")), _norm_team(getattr(m, "away_team", "")), int(fs[0]), int(fs[1])))
    games.sort(key=lambda x: x[0], reverse=True)
    w = d = l = 0
    used = 0
    for _, home, away, hg, ag in games:
        if home != t and away != t:
            continue
        used += 1
        if hg == ag:
            d += 1
        else:
            won = (home == t and hg > ag) or (away == t and ag > hg)
            w += 1 if won else 0
            l += 0 if won else 1
        if used >= int(n):
            break
    return (w, d, l)


def _h2h_for_team(matches: list[Any], championship: str, team: str, opponent: str, n: int) -> tuple[int, int, int]:
    champ = str(championship or "").strip()
    t = _norm_team(team)
    o = _norm_team(opponent)
    games: list[tuple[float, str, str, int, int]] = []
    for m in matches:
        if str(getattr(m, "championship", "") or "").strip() != champ:
            continue
        if str(getattr(m, "status", "") or "").upper() != "FINISHED":
            continue
        if getattr(m, "kickoff_unix", None) is None:
            continue
        fs = _extract_final_score(getattr(m, "meta", None))
        if fs is None:
            continue
        home = _norm_team(getattr(m, "home_team", ""))
        away = _norm_team(getattr(m, "away_team", ""))
        if {home, away} != {t, o}:
            continue
        games.append((float(m.kickoff_unix), home, away, int(fs[0]), int(fs[1])))
    games.sort(key=lambda x: x[0], reverse=True)
    w = d = l = 0
    used = 0
    for _, home, away, hg, ag in games:
        used += 1
        if hg == ag:
            d += 1
        else:
            won = (home == t and hg > ag) or (away == t and ag > hg)
            w += 1 if won else 0
            l += 0 if won else 1
        if used >= int(n):
            break
    return (w, d, l)


@router.get("/api/v1/explain/team", response_model=ExplainResponse)
async def explain_team(request: Request, championship: str, team: str) -> ExplainResponse:
    state = request.app.state.app_state
    matches = await state.list_matches()
    ratings = _read_ratings()

    strength_pct, strength_vs_avg_pp = _strength_stats_for_team(ratings, championship, team)
    w, d, l = _form_for_team(matches, championship, team, 7)

    why: list[str] = []
    risks: list[str] = []

    if strength_pct is not None and strength_vs_avg_pp is not None:
        if strength_vs_avg_pp >= 0:
            why.append(f"Forza sopra la media di {abs(strength_vs_avg_pp):.1f} p.p. (indice forza {strength_pct:.1f}%)")
        else:
            risks.append(f"Forza sotto la media di {abs(strength_vs_avg_pp):.1f} p.p. (indice forza {strength_pct:.1f}%)")
    else:
        risks.append("Forza squadra non disponibile (team non presente nei rating)")

    total = int(w + d + l)
    if total > 0:
        why.append(f"Forma recente: {w}V-{d}N-{l}P negli ultimi {total} match")
    else:
        risks.append("Forma recente non disponibile (mancano match FINISHED)")

    return ExplainResponse(
        generated_at_utc=datetime.now(timezone.utc),
        championship=str(championship),
        match_id=None,
        team=_norm_team(team),
        pick=None,
        why=why,
        risks=risks,
        strength=ExplainTeamStrength(team=_norm_team(team), strength_pct=strength_pct, strength_vs_avg_pp=strength_vs_avg_pp),
        form=ExplainForm(last_n=7, w=int(w), d=int(d), l=int(l)),
        context=ExplainContext(home=None, opponent_team=None, h2h_last_n=None, h2h_w=None, h2h_d=None, h2h_l=None),
    )


@router.get("/api/v1/explain/match", response_model=ExplainResponse)
async def explain_match(request: Request, match_id: str) -> ExplainResponse:
    state = request.app.state.app_state
    m = await state.get_match(str(match_id))
    if m is None:
        return ExplainResponse(
            generated_at_utc=datetime.now(timezone.utc),
            championship="",
            match_id=str(match_id),
            team="",
            pick=None,
            why=[],
            risks=["Match non trovato"],
            strength=None,
            form=None,
            context=None,
        )

    champ = str(getattr(m, "championship", "") or "")
    home_team = _norm_team(getattr(m, "home_team", ""))
    away_team = _norm_team(getattr(m, "away_team", ""))
    probs = getattr(m, "probabilities", None)
    p1 = float(probs.get("home_win", 0.0)) if isinstance(probs, dict) else 0.0
    px = float(probs.get("draw", 0.0)) if isinstance(probs, dict) else 0.0
    p2 = float(probs.get("away_win", 0.0)) if isinstance(probs, dict) else 0.0
    pick = "home_win" if (p1 >= px and p1 >= p2) else "draw" if (px >= p1 and px >= p2) else "away_win"
    team = home_team if pick == "home_win" else away_team if pick == "away_win" else "Pareggio"

    ratings = _read_ratings()
    matches = await state.list_matches()
    strength_pct, strength_vs_avg_pp = _strength_stats_for_team(ratings, champ, team if pick != "draw" else home_team)

    w, d, l = _form_for_team(matches, champ, team if pick != "draw" else home_team, 7)
    total = int(w + d + l)

    ctx = ExplainContext(home=(pick == "home_win"), opponent_team=(away_team if pick == "home_win" else home_team if pick == "away_win" else None))
    h2h_w = h2h_d = h2h_l = 0
    if ctx.opponent_team is not None and team != "Pareggio":
        h2h_w, h2h_d, h2h_l = _h2h_for_team(matches, champ, team, ctx.opponent_team, 5)
        ctx.h2h_last_n = int(h2h_w + h2h_d + h2h_l)
        ctx.h2h_w = int(h2h_w)
        ctx.h2h_d = int(h2h_d)
        ctx.h2h_l = int(h2h_l)

    why: list[str] = []
    risks: list[str] = []

    if pick == "draw":
        why.append("Esiti bilanciati: il modello non vede un favorito netto")

    if strength_pct is not None and strength_vs_avg_pp is not None:
        if strength_vs_avg_pp >= 0:
            why.append(f"Forza squadra sopra la media di {abs(strength_vs_avg_pp):.1f} p.p.")
        else:
            risks.append(f"Forza squadra sotto la media di {abs(strength_vs_avg_pp):.1f} p.p.")
    else:
        risks.append("Forza squadra non disponibile (team non presente nei rating)")

    if total > 0:
        why.append(f"Forma recente: {w}V-{d}N-{l}P negli ultimi {total} match")

    if pick in {"home_win", "away_win"}:
        why.append("Contesto: " + ("partita in casa" if pick == "home_win" else "partita in trasferta"))

    if ctx.h2h_last_n is not None and ctx.h2h_last_n > 0 and pick != "draw":
        if int(ctx.h2h_w or 0) > int(ctx.h2h_l or 0):
            why.append(f"Storico recente favorevole: {ctx.h2h_w}V-{ctx.h2h_d}N-{ctx.h2h_l}P (ultimi {ctx.h2h_last_n})")
        else:
            risks.append(f"Storico recente non favorevole: {ctx.h2h_w}V-{ctx.h2h_d}N-{ctx.h2h_l}P (ultimi {ctx.h2h_last_n})")

    spread = max(p1, px, p2) - sorted([p1, px, p2])[-2]
    if spread < 0.06:
        risks.append("Alta variabilità: probabilità molto vicine tra loro")

    return ExplainResponse(
        generated_at_utc=datetime.now(timezone.utc),
        championship=str(champ),
        match_id=str(match_id),
        team=str(team),
        pick=str(pick),
        why=why,
        risks=risks,
        strength=ExplainTeamStrength(team=str(team), strength_pct=strength_pct, strength_vs_avg_pp=strength_vs_avg_pp),
        form=ExplainForm(last_n=7, w=int(w), d=int(d), l=int(l)),
        context=ctx,
    )


@router.get("/api/v1/insights/teams-to-play", response_model=TeamsToPlayResponse)
async def teams_to_play(request: Request) -> TeamsToPlayResponse:
    ratings = _read_ratings()
    if not ratings:
        return TeamsToPlayResponse(generated_at_utc=datetime.now(timezone.utc), items=[])

    if not hasattr(request.app.state, "app_state"):
        request.app.state.app_state = AppState()
    state = request.app.state.app_state
    tenant_id = _tenant_id_from_request(request)
    tenant_row = await state.get_tenant_config(tenant_id=tenant_id)
    tenant_cfg0 = tenant_row.get("config") if isinstance(tenant_row, dict) else None
    tenant_cfg = tenant_cfg0 if isinstance(tenant_cfg0, dict) else {}
    compliance = tenant_cfg.get("compliance") if isinstance(tenant_cfg.get("compliance"), dict) else {}
    _apply_region_policy(request, compliance)
    filters = tenant_cfg.get("filters") if isinstance(tenant_cfg.get("filters"), dict) else {}
    raw_vis = filters.get("visible_championships")
    allow_champs = [str(x).strip().lower() for x in (raw_vis if isinstance(raw_vis, list) else []) if str(x).strip()]
    allow_set = set(allow_champs) if allow_champs else set()
    matches = await state.list_matches()

    finished_by_champ: dict[str, list] = {}
    for m in matches:
        if str(getattr(m, "status", "") or "").upper() != "FINISHED":
            continue
        if getattr(m, "kickoff_unix", None) is None:
            continue
        fs = _extract_final_score(getattr(m, "meta", None))
        if fs is None:
            continue
        finished_by_champ.setdefault(str(getattr(m, "championship", "") or ""), []).append((float(m.kickoff_unix), m.home_team, m.away_team, fs[0], fs[1]))

    items: list[TeamsToPlayItem] = []
    for champ, strengths in ratings.items():
        if allow_set and str(champ).strip().lower() not in allow_set:
            continue
        games = finished_by_champ.get(champ, [])
        games.sort(key=lambda x: x[0], reverse=True)

        recent: dict[str, list[float]] = {t: [] for t in strengths.keys()}
        for _, home, away, hg, ag in games:
            if home in recent and len(recent[home]) < 8:
                if hg > ag:
                    recent[home].append(1.0)
                elif hg == ag:
                    recent[home].append(0.5)
                else:
                    recent[home].append(0.0)
            if away in recent and len(recent[away]) < 8:
                if ag > hg:
                    recent[away].append(1.0)
                elif ag == hg:
                    recent[away].append(0.5)
                else:
                    recent[away].append(0.0)
            if all(len(v) >= 8 for v in recent.values()):
                break

        scored: list[tuple[str, float, float, float]] = []
        for team, strength in strengths.items():
            s_pct = _strength_to_pct(float(strength))
            last = recent.get(team, [])
            f_pct = (sum(last) / len(last)) if last else 0.5
            success = 100.0 * (0.65 * _clamp01(s_pct) + 0.35 * _clamp01(float(f_pct)))
            if success < 0.0:
                success = 0.0
            if success > 100.0:
                success = 100.0
            scored.append((team, round(float(success), 1), round(float(s_pct) * 100.0, 1), round(float(f_pct) * 100.0, 1)))

        scored.sort(key=lambda x: (-x[1], x[0].lower()))
        top3 = [TeamToPlay(team=t, success_pct=s, strength_pct=sp, form_pct=fp) for t, s, sp, fp in scored[:3]]
        items.append(TeamsToPlayItem(championship=_championship_display_name(champ), top3=top3))

    items.sort(key=lambda x: x.championship.lower())
    return TeamsToPlayResponse(generated_at_utc=datetime.now(timezone.utc), items=items)
