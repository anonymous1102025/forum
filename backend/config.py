from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fetch_hour_utc: int = 6
    fetch_on_startup: bool = True
    cors_origins: str = "http://localhost:3000 http://localhost:5173"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split() if o.strip()]


settings = Settings()
