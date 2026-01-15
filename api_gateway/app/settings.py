import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORECAST_", env_file=".env", extra="ignore")

    app_name: str = "Forecast Master System API"
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    cors_allow_origin_regex: str | None = None
    simulate_live_updates: bool = True
    live_tick_seconds: int = 30
    real_data_only: bool = False
    data_provider: str = "mock"

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
    football_data_max_competitions_per_seed: int = 1
    fixtures_days_ahead: int = 90
    ratings_path: str = "data/team_ratings.json"
    historical_start_season: int = 2015
    historical_end_season: int = 2025
    local_data_dir: str = ".."
    local_calendar_filename: str = "Calendari_Calcio_2025_2026.xlsx"

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
