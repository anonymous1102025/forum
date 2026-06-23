from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Scheduler
    fetch_hour_utc: int = 6
    fetch_on_startup: bool = True

    # CORS
    cors_origins: str = "http://localhost:3000 http://localhost:5173"

    # Auth
    auth_user: str = "admin"
    auth_password: str = "changeme"
    jwt_secret: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # Storage — persistent disk on Render, local data/ in dev
    data_dir: str = "data"

    # GA4 single-account bootstrap (used when accounts.json doesn't exist)
    ga4_property_id: str = ""
    ga4_account_name: str = ""
    ga4_credentials_path: str = ""   # path to service account JSON (Render Secret File)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split() if o.strip()]


settings = Settings()
