from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass
class LeagueSpec:
    championship: str
    source_xlsx: str


LEAGUES: list[LeagueSpec] = [
    LeagueSpec(championship="serie_a", source_xlsx="SerieA_Matches_2015-2025.xlsx"),
    LeagueSpec(championship="premier_league", source_xlsx="PremierLeague_Matches_2015-2025.xlsx"),
    LeagueSpec(championship="la_liga", source_xlsx="Liga_Matches_2015-2025.xlsx"),
    LeagueSpec(championship="bundesliga", source_xlsx="Bundesliga_Matches_2015-2025.xlsx"),
]

LABELS_1X2 = ["H", "D", "A"]


def _safe_season_year(v: Any) -> int | None:
    s = str(v or "").strip()
    if not s:
        return None
    head = s.split("/")[0].strip()
    if head.isdigit():
        return int(head)
    return None


def _brier_multiclass(y_true: np.ndarray, proba: np.ndarray, labels: list[str]) -> float:
    n = len(y_true)
    if n == 0:
        return float("nan")
    idx = {lab: i for i, lab in enumerate(labels)}
    y = np.zeros_like(proba, dtype=float)
    for r, lab in enumerate(y_true):
        if lab in idx:
            y[r, idx[lab]] = 1.0
    return float(np.mean(np.sum((proba - y) ** 2, axis=1)))


def _points_for_result(ftr: str) -> tuple[int, int]:
    if ftr == "H":
        return 3, 0
    if ftr == "A":
        return 0, 3
    return 1, 1


def _build_features(df: pd.DataFrame, *, window: int = 5) -> pd.DataFrame:
    out = df.copy()
    out["home_elo_pre"] = np.nan
    out["away_elo_pre"] = np.nan
    out["elo_diff"] = np.nan
    out[f"home_pts_last{window}"] = np.nan
    out[f"away_pts_last{window}"] = np.nan
    out[f"home_gf_last{window}"] = np.nan
    out[f"home_ga_last{window}"] = np.nan
    out[f"away_gf_last{window}"] = np.nan
    out[f"away_ga_last{window}"] = np.nan
    out["home_days_rest"] = np.nan
    out["away_days_rest"] = np.nan
    out["rest_diff"] = np.nan

    ratings: dict[str, float] = {}
    hist: dict[str, list[tuple[datetime, int, int, int]]] = {}
    last_played: dict[str, datetime] = {}

    base_rating = 1500.0
    home_adv = 55.0

    def k_for_season_year(season_year: int | None) -> float:
        if season_year is None:
            return 22.0
        return 30.0 if season_year >= 2022 else 22.0

    def expected(r_a: float, r_b: float) -> float:
        return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))

    for i, r in out.iterrows():
        h = str(r["HomeTeam"]).strip()
        a = str(r["AwayTeam"]).strip()
        dt = r["Date"]
        if not isinstance(dt, datetime):
            dt = pd.to_datetime(dt).to_pydatetime()

        rh = float(ratings.get(h, base_rating))
        ra = float(ratings.get(a, base_rating))
        out.at[i, "home_elo_pre"] = rh
        out.at[i, "away_elo_pre"] = ra
        out.at[i, "elo_diff"] = rh - ra

        def lastN(team: str) -> tuple[float, float, float]:
            rows = hist.get(team, [])
            if not rows:
                return (float("nan"), float("nan"), float("nan"))
            last = rows[-window:]
            pts = sum(x[1] for x in last)
            gf = sum(x[2] for x in last)
            ga = sum(x[3] for x in last)
            return (float(pts), float(gf), float(ga))

        ph, gfh, gah = lastN(h)
        pa, gfa, gaa = lastN(a)
        out.at[i, f"home_pts_last{window}"] = ph
        out.at[i, f"home_gf_last{window}"] = gfh
        out.at[i, f"home_ga_last{window}"] = gah
        out.at[i, f"away_pts_last{window}"] = pa
        out.at[i, f"away_gf_last{window}"] = gfa
        out.at[i, f"away_ga_last{window}"] = gaa

        if h in last_played:
            out.at[i, "home_days_rest"] = float((dt - last_played[h]).days)
        if a in last_played:
            out.at[i, "away_days_rest"] = float((dt - last_played[a]).days)
        if pd.notna(out.at[i, "home_days_rest"]) and pd.notna(out.at[i, "away_days_rest"]):
            out.at[i, "rest_diff"] = float(out.at[i, "home_days_rest"] - out.at[i, "away_days_rest"])

        ftr = str(r["FTR"]).strip()
        if ftr not in {"H", "D", "A"}:
            continue

        hg = r["FTHG"]
        ag = r["FTAG"]
        if not isinstance(hg, (int, float)) or not isinstance(ag, (int, float)):
            continue

        pts_h, pts_a = _points_for_result(ftr)
        hist.setdefault(h, []).append((dt, pts_h, int(hg), int(ag)))
        hist.setdefault(a, []).append((dt, pts_a, int(ag), int(hg)))
        last_played[h] = dt
        last_played[a] = dt

        season_year = _safe_season_year(r.get("Season"))
        k = k_for_season_year(season_year)
        exp_h = expected(rh + home_adv, ra)
        score_h = 1.0 if ftr == "H" else 0.0 if ftr == "A" else 0.5
        score_a = 1.0 - score_h if ftr != "D" else 0.5
        ratings[h] = rh + k * (score_h - exp_h)
        ratings[a] = ra + k * (score_a - (1.0 - exp_h))

    out["season_year"] = out["Season"].apply(_safe_season_year).astype("float")
    out["month"] = out["Date"].dt.month.astype("float")
    out["weekday"] = out["Date"].dt.weekday.astype("float")
    return out


def _load_league_xlsx(path: Path) -> pd.DataFrame:
    need_sets = [
        {"Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"},
        {"Season", "MatchDate", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"},
    ]

    header_row = 1
    preview = pd.read_excel(path, header=None, nrows=6)
    for i in range(len(preview)):
        row = {str(x).strip() for x in preview.iloc[i].tolist() if str(x).strip() and str(x).strip() != "nan"}
        if any(need.issubset(row) for need in need_sets):
            header_row = i
            break

    df = pd.read_excel(path, header=header_row)
    df = df.rename(columns={c: str(c).strip() for c in df.columns})
    if "MatchDate" in df.columns and "Date" not in df.columns:
        df = df.rename(columns={"MatchDate": "Date"})

    need = need_sets[0]
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"missing_columns:{','.join(sorted(missing))}")

    df["Date"] = pd.to_datetime(df["Date"])
    df["HomeTeam"] = df["HomeTeam"].astype(str).str.strip()
    df["AwayTeam"] = df["AwayTeam"].astype(str).str.strip()
    df["FTR"] = df["FTR"].astype(str).str.strip()
    df = df[df["FTR"].isin(LABELS_1X2)].copy()
    df.sort_values(["Date", "MatchID"] if "MatchID" in df.columns else ["Date"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def train_one_league(*, league: LeagueSpec, base_dir: Path, out_dir: Path, split_ratio: float) -> dict[str, Any]:
    src = (base_dir / league.source_xlsx).resolve()
    df0 = _load_league_xlsx(src)
    df = _build_features(df0, window=5)

    feature_cols = [
        "home_elo_pre",
        "away_elo_pre",
        "elo_diff",
        "home_days_rest",
        "away_days_rest",
        "rest_diff",
        "home_pts_last5",
        "away_pts_last5",
        "home_gf_last5",
        "home_ga_last5",
        "away_gf_last5",
        "away_ga_last5",
        "season_year",
        "month",
        "weekday",
    ]

    X = df[feature_cols]
    y = df["FTR"].to_numpy()
    n = len(df)
    split = int(math.floor(n * split_ratio))
    split = max(1, min(n - 1, split))
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y[:split], y[split:]

    pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, multi_class="multinomial")),
        ]
    )
    pipe.fit(X_train, y_train)

    proba = pipe.predict_proba(X_test)
    acc = float(accuracy_score(y_test, pipe.predict(X_test)))
    ll = float(log_loss(y_test, proba, labels=LABELS_1X2))
    brier = float(_brier_multiclass(y_test, proba, LABELS_1X2))

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"model_1x2_{league.championship}.joblib"
    metrics_path = out_dir / f"metrics_1x2_{league.championship}.json"

    joblib.dump(
        {
            "pipeline": pipe,
            "feature_cols": feature_cols,
            "labels": LABELS_1X2,
            "championship": league.championship,
        },
        model_path,
    )

    payload = {
        "championship": league.championship,
        "source": str(src),
        "n_rows": int(n),
        "split_ratio": float(split_ratio),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "metrics": {"accuracy": acc, "log_loss": ll, "brier": brier},
        "feature_cols": feature_cols,
        "labels": LABELS_1X2,
        "generated_at_utc": datetime.utcnow().isoformat(),
    }
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="data/models")
    ap.add_argument("--split-ratio", type=float, default=0.8)
    args = ap.parse_args()

    out_dir = Path(args.out)
    split_ratio = float(args.split_ratio)
    base_dir = Path(__file__).resolve().parents[2]

    all_metrics: dict[str, Any] = {"generated_at_utc": datetime.utcnow().isoformat(), "leagues": {}}
    for league in LEAGUES:
        row = train_one_league(league=league, base_dir=base_dir, out_dir=out_dir, split_ratio=split_ratio)
        all_metrics["leagues"][league.championship] = row

    (out_dir / "metrics_1x2_all.json").write_text(json.dumps(all_metrics, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
