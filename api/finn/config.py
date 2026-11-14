"""All configuration comes from environment variables (or the repo-root .env).

Every external service is swappable by changing env vars only; every value has a
working local default so a fresh clone runs without any account.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://finn:finn@localhost:5432/finn"
    cors_origins: str = "http://localhost:3000"
    finn_env: str = "local"

    ollama_base_url: str = "http://localhost:11434/v1"
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    openrouter_api_key: str = ""
    gemini_api_key: str = ""

    # Web Push: a standard P-256 VAPID pair. The private key stays on the API host.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:owner@example.invalid"

    # live research jobs: the API starts a GitHub Actions run when no laptop worker is online
    github_dispatch_token: str = ""
    github_repo: str = ""  # owner/name; on Render, RENDER_GIT_REPO_SLUG is used when unset
    github_ref: str = "main"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
