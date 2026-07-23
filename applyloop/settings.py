from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///applyloop.db"
    anthropic_api_key: str = ""
    config_dir: Path = Path("config")
    score_threshold: int = 70
    llm_backend: str = "anthropic_api"
    claude_code_binary: str = "claude"
    claude_code_timeout: int = 180


@lru_cache
def get_settings() -> Settings:
    return Settings()
