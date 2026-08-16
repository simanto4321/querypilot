"""Configuration. Runs fully offline by default with a deterministic NL->SQL
provider; set ``QUERYPILOT_LLM_PROVIDER=openai`` (+ API key) to use a hosted LLM.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QUERYPILOT_", env_file=".env", extra="ignore")

    # Analytics warehouse under query. Defaults to a zero-setup SQLite file.
    warehouse_url: str = "sqlite:///./querypilot.db"

    # Provider for NL->SQL: "deterministic" (offline, default) or "openai".
    llm_provider: str = "deterministic"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Safety guardrails.
    max_rows: int = 1000
    # Estimated row scan above which a query needs human approval before running.
    approval_row_threshold: int = 50000

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
