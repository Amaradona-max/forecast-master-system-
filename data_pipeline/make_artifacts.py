from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from data_pipeline.train_1x2_models import (
    FOOTBALL_DATA_LEAGUE_TO_CHAMPIONSHIP,
    LEAGUES,
    _resolve_input_path,
    train_one_league,
    train_one_league_csv,
    train_one_league_local_calendar,
)


def _normalize_tokens(items: list[str] | None) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for item in items:
        parts = [p.strip() for p in str(item).replace(";", ",").split(",")]
        out.extend([p for p in parts if p])
    return out


def _resolve_leagues(tokens: list[str]) -> list[str]:
    if not tokens:
        return [spec.championship for spec in LEAGUES]
    by_champ = {spec.championship: spec for spec in LEAGUES}
    out: list[str] = []
    for tok in tokens:
        if tok in by_champ:
            out.append(tok)
        else:
            raise ValueError(f"unknown_league:{tok}")
    return out


def _resolve_csv_leagues(tokens: list[str]) -> list[tuple[str, str]]:
    rev = {v: k for k, v in FOOTBALL_DATA_LEAGUE_TO_CHAMPIONSHIP.items()}
    if not tokens:
        return [(champ, code) for code, champ in FOOTBALL_DATA_LEAGUE_TO_CHAMPIONSHIP.items()]
    out: list[tuple[str, str]] = []
    for tok in tokens:
        if tok in FOOTBALL_DATA_LEAGUE_TO_CHAMPIONSHIP:
            out.append((FOOTBALL_DATA_LEAGUE_TO_CHAMPIONSHIP[tok], tok))
        elif tok in rev:
            out.append((tok, rev[tok]))
        else:
            raise ValueError(f"unknown_league:{tok}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default=os.getenv("ARTIFACT_DIR", "data/models"))
    ap.add_argument("--split-ratio", type=float, default=0.8)
    ap.add_argument("--source", type=str, default="xlsx", choices=["xlsx", "csv", "local_calendar"])
    ap.add_argument("--dataset-dir", type=str, default="out")
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--leagues", type=str, nargs="*", default=[])
    ap.add_argument("--calendar-file", type=str, default="Calendari_Calcio_2025_2026.xlsx")
    ap.add_argument("--season-label", type=str, default="2025/2026")
    args = ap.parse_args()

    out_dir = Path(args.out)
    split_ratio = float(args.split_ratio)
    base_dir = Path(__file__).resolve().parents[2]

    tokens = _normalize_tokens(args.leagues)
    all_metrics: dict[str, Any] = {"generated_at_utc": datetime.utcnow().isoformat(), "leagues": {}}

    if str(args.source) == "local_calendar":
        calendar_path = _resolve_input_path(base_dir=base_dir, filename=str(args.calendar_file))
        leagues = _resolve_leagues(tokens)
        by_champ = {spec.championship: spec for spec in LEAGUES}
        for champ in leagues:
            league = by_champ[champ]
            row = train_one_league_local_calendar(
                league=league,
                base_dir=base_dir,
                calendar_path=calendar_path,
                out_dir=out_dir,
                split_ratio=split_ratio,
                season_label=str(args.season_label),
            )
            all_metrics["leagues"][league.championship] = row
    elif str(args.source) == "csv":
        dataset_dir = (base_dir / str(args.dataset_dir)).resolve()
        season = int(args.season)
        leagues = _resolve_csv_leagues(tokens)
        for champ, code in leagues:
            csv_path = dataset_dir / f"dataset_{code}_{season}.csv"
            row = train_one_league_csv(championship=champ, csv_path=csv_path, out_dir=out_dir, split_ratio=split_ratio)
            all_metrics["leagues"][champ] = row
    else:
        leagues = _resolve_leagues(tokens)
        by_champ = {spec.championship: spec for spec in LEAGUES}
        for champ in leagues:
            league = by_champ[champ]
            row = train_one_league(league=league, base_dir=base_dir, out_dir=out_dir, split_ratio=split_ratio)
            all_metrics["leagues"][league.championship] = row

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics_1x2_all.json").write_text(
        json.dumps(all_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
