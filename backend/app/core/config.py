"""
Centralized app configuration, loaded from environment variables / .env.

Every later step reads its own settings from here rather than calling
os.environ directly, so the ingestion, geospatial, model, and agent modules
all share one source of truth for connection strings and API keys.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    environment: str = "development"
    backend_cors_origins: str = "http://localhost:3000"

    # --- Database / cache ---
    database_url: str = "postgresql+psycopg2://urbanair:urbanair@localhost:5432/urbanair"
    redis_url: str = "redis://localhost:6379/0"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 7200

    # --- Data source API keys (Step 2) ---
    openaq_api_key: str = ""
    nasa_firms_map_key: str = ""
    copernicus_cdse_username: str = ""
    copernicus_cdse_password: str = ""

    # --- LLM provider (Step 6) ---
    llm_provider: str = "groq"
    groq_api_key: str = ""
    anthropic_api_key: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
