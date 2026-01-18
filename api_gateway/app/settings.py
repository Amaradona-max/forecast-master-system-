import json
import os
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORECAST_", env_file=".env", extra="ignore")

    app_name: str = "Forecast Master System API"
    admin_token: str | None = None
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://localhost:3001"]
    cors_allow_origin_regex: str | None = None
    simulate_live_updates: bool = True
    live_tick_seconds: int = 30
    real_data_only: bool = False
    data_provider: str = "mock"
    state_db_path: str = "/tmp/forecast_state.sqlite3" if os.getenv("VERCEL") else "data/forecast_state.sqlite3"
    calibration_lookback_days: int = 365

    api_football_key: str | None = None
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_league_ids: dict[str, int] = {
        "serie_a": 135,
        "premier_league": 39,
        "la_liga": 140,
        "bundesliga": 78,
        "eliteserien": 103,
    }
    api_football_season_years: dict[str, int] = {
        "serie_a": 2025,
        "premier_league": 2025,
        "la_liga": 2025,
        "bundesliga": 2025,
        "eliteserien": 2026,
    }

    football_data_key: str | None = None
    football_data_base_url: str = "https://api.football-data.org/v4"
    football_data_competition_codes: dict[str, str] = {
        "serie_a": "SA",
        "premier_league": "PL",
        "la_liga": "PD",
        "bundesliga": "BL1",
    }
    football_data_max_competitions_per_seed: int = 4
    fixtures_days_ahead: int = 90
    fixtures_refresh_days_back: int = 3
    fixtures_refresh_days_ahead: int = 0
    fixtures_refresh_cache_ttl_seconds: int = 600
    fixtures_refresh_interval_seconds: int = 600
    fixtures_season_start_utc: str = "2025-08-01T00:00:00Z"
    fixtures_season_end_utc: str = "2026-06-30T23:59:59Z"
    fixtures_season_cache_ttl_seconds: int = 43200
    fixtures_season_interval_seconds: int = 86400
    ratings_refresh_enabled: bool = True
    ratings_refresh_interval_seconds: int = 86400
    ratings_weekend_refresh_interval_seconds: int = 0
    ratings_path: str = "data/team_ratings.json"
    historical_start_season: int = 2015
    historical_end_season: int = 2025
    local_data_dir: str = ".."
    local_calendar_filename: str = "Calendari_Calcio_2025_2026.xlsx"

    notifications_enabled: bool = False
    notifications_interval_seconds: int = 300
    notifications_match_imminent_hours: int = 24
    notifications_team_success_threshold_pct: float = 75.0
    notifications_team_confidence_threshold_pct: float = 70.0
    notifications_value_index_threshold: float = 10.0

    notifications_push_enabled: bool = True

    notifications_email_enabled: bool = False
    notifications_email_smtp_host: str | None = None
    notifications_email_smtp_port: int = 587
    notifications_email_smtp_user: str | None = None
    notifications_email_smtp_password: str | None = None
    notifications_email_from: str | None = None
    notifications_email_to: str | None = None

    @field_validator("data_provider", mode="before")
    @classmethod
    def _normalize_data_provider(cls, v: object) -> object:
        if v is None:
            return v
        s = str(v).strip()
        return s.lower()

    @model_validator(mode="after")
    def _enforce_real_data_only(self) -> "Settings":
        if not bool(self.real_data_only):
            return self

        if str(self.data_provider or "").strip().lower() != "football_data":
            raise ValueError("real_data_only_requires_football_data_provider")

        if not str(self.football_data_key or "").strip():
            raise ValueError("football_data_key_missing")

        if not isinstance(self.football_data_competition_codes, dict) or not self.football_data_competition_codes:
            raise ValueError("football_data_config_missing")

        return self

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_cors_allow_origins(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
                if isinstance(parsed, str):
                    s = parsed.strip()
            except Exception:
                pass
            parts = [p.strip() for p in s.split(",")]
            return [p for p in parts if p]
        return v


settings = Settings()
