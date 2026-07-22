from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///applyloop.db"
    anthropic_api_key: str = ""
    config_dir: Path = Path("config")
    score_threshold: int = 70


@lru_cache
def get_settings() -> Settings:
    return Settings()
