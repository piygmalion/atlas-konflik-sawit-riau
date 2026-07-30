"""Konfigurasi backend Atlas Konflik Sawit Riau."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_ROOT = BACKEND_ROOT.parent
DEFAULT_DATA_DIR = WEBSITE_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    sync_api_key: str = ""
    data_dir: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8787
    cors_origins: str = (
        "http://127.0.0.1:8080,http://localhost:8080,"
        "https://piygmalion.github.io"
    )

    @property
    def data_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).expanduser().resolve()
        return DEFAULT_DATA_DIR

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
