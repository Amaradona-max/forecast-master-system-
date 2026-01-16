from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Championship = Literal["serie_a", "premier_league", "la_liga", "bundesliga", "eliteserien"]


class MatchInput(BaseModel):
    match_id: str = Field(min_length=1, max_length=160)
    championship: Championship
    home_team: str = Field(min_length=1, max_length=80)
    away_team: str = Field(min_length=1, max_length=80)
    kickoff_utc: datetime | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class BatchPredictionRequest(BaseModel):
    matches: list[MatchInput] = Field(min_length=1)


class MatchPrediction(BaseModel):
    match_id: str
    championship: Championship
    home_team: str
    away_team: str
    status: str
    updated_at_unix: float
    probabilities: dict[str, float]
    explain: dict[str, Any] = Field(default_factory=dict)


class BatchPredictionResponse(BaseModel):
    generated_at_utc: datetime
    predictions: list[MatchPrediction]


class LiveProbabilitiesResponse(BaseModel):
    match_id: str
    status: str
    kickoff_unix: float | None = None
    updated_at_unix: float
    probabilities: dict[str, float]
    meta: dict[str, Any] = Field(default_factory=dict)


class SeasonAccuracyPoint(BaseModel):
    date_utc: datetime
    brier: float
    log_loss: float
    roc_auc: float
    roi_simulated: float


class SeasonAccuracyResponse(BaseModel):
    championship: Championship | Literal["all"]
    points: list[SeasonAccuracyPoint]


class CalibrationBin(BaseModel):
    bin_lo: float
    bin_hi: float
    predicted_avg: float
    observed_rate: float
    count: int


class CalibrationWindowMetrics(BaseModel):
    window: int | Literal["season"]
    n: int
    log_loss: float
    brier: float
    ece: float
    bins: list[CalibrationBin] = Field(default_factory=list)


class CalibrationMetricsResponse(BaseModel):
    championship: Championship
    metrics: CalibrationWindowMetrics


class CalibrationSummaryResponse(BaseModel):
    championship: Championship
    last_50: CalibrationWindowMetrics
    last_200: CalibrationWindowMetrics
    season_to_date: CalibrationWindowMetrics


class OverviewMatch(BaseModel):
    match_id: str
    championship: Championship
    home_team: str
    away_team: str
    status: str
    matchday: int | None = None
    kickoff_unix: float | None = None
    updated_at_unix: float
    probabilities: dict[str, float]
    confidence: float
    explain: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    final_score: dict[str, int] | None = None


class MatchdayBlock(BaseModel):
    matchday_number: int | None = None
    matchday_label: str
    matches: list[OverviewMatch]


class ChampionshipOverview(BaseModel):
    championship: Championship
    title: str
    accuracy_target: str | None = None
    key_features: list[str] = Field(default_factory=list)
    matchdays: list[MatchdayBlock] = Field(default_factory=list)
    top_matches: list[OverviewMatch] = Field(default_factory=list)
    to_play_ge_70: list[OverviewMatch] = Field(default_factory=list)
    finished: list[OverviewMatch] = Field(default_factory=list)


class ChampionshipsOverviewResponse(BaseModel):
    generated_at_utc: datetime
    championships: list[ChampionshipOverview]
