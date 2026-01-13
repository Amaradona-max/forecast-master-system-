from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORECAST_", env_file=".env", extra="ignore")

    app_name: str = "Forecast Master System API"
    cors_allow_origins: list[str] = ["http://localhost:3000"]
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
    fixtures_days_ahead: int = 90
    ratings_path: str = "data/team_ratings.json"
    historical_start_season: int = 2015
    historical_end_season: int = 2025
    local_data_dir: str = ".."
    local_calendar_filename: str = "Calendari_Calcio_2025_2026.xlsx"


settings = Settings()
