"""Runtime configuration loaded from the environment.

Application code should call ``get_settings()``. Tests should construct
``Settings`` directly so each test controls its own environment.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentName = Literal["local", "test", "production"]


class Settings(BaseSettings):
    """Typed settings for one running process.

    ``llm_enabled`` defaults to false so the platform runs without an API key.
    A ``.env`` file in the working directory overrides these defaults.
    Environment variables override the file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Governance & Risk Assessment Platform"
    app_env: EnvironmentName = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://127.0.0.1:5432/ai_governance"

    llm_enabled: bool = False
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None

    data_dir: str = "data"
    cellar_base_url: str = "http://publications.europa.eu/resource/celex"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
