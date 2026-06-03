"""Application configuration from environment variables."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# Langfuse (and other libs) read os.environ; pydantic alone does not populate it.
load_dotenv(_ENV_FILE, override=False)

# Langfuse SDK reads LANGFUSE_HOST only (defaults to EU). Must run before any
# langfuse import / get_client() call — @observe initializes the client early.
if os.environ.get("LANGFUSE_BASE_URL") and not os.environ.get("LANGFUSE_HOST"):
    os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"].rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://capterra:capterra@localhost:5432/capterra",
        validation_alias="DATABASE_URL",
    )
    openai_key: str = Field(default="", validation_alias="OPENAI_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="EMBEDDING_MODEL")
    firecrawl_api_key: str = Field(default="", validation_alias="FIRECRAWL_API_KEY")
    capterra_cookie: str = Field(default="", validation_alias="CAPTERRA_COOKIE")
    flaresolverr_url: str = Field(default="", validation_alias="FLARESOLVERR_URL")

    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="", validation_alias="LANGFUSE_HOST")
    langfuse_base_url: str = Field(default="", validation_alias="LANGFUSE_BASE_URL")

    fetch_timeout: float = 60.0
    gradio_port: int = Field(default=7860, validation_alias="GRADIO_PORT")
    gradio_server_name: str = Field(default="127.0.0.1", validation_alias="GRADIO_SERVER_NAME")
    gradio_skip_localhost_check: bool = Field(
        default=False,
        validation_alias="GRADIO_SKIP_LOCALHOST_CHECK",
    )
    cors_origins: str = Field(default="*", validation_alias="CORS_ORIGINS")

    def cors_origins_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value == "*":
            return ["*"]
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
