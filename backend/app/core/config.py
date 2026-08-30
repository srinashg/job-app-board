"""Application configuration loaded from the environment."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- General -----------------------------------------------------------
    environment: str = "development"
    project_name: str = "Job Application Board"
    api_v1_prefix: str = "/api/v1"

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/jobboard"

    # --- Security ----------------------------------------------------------
    secret_key: str = "dev-secret-change-me"
    # Fernet key used to encrypt personal data at rest. Generated per install.
    encryption_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # --- OAuth 2.0 ---------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:3000/auth/callback/google"
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"

    # --- CORS --------------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- Storage -----------------------------------------------------------
    resume_storage_dir: str = "./var/resumes"
    max_resume_bytes: int = 5 * 1024 * 1024

    # --- Recommendations ---------------------------------------------------
    batch_size: int = 5
    job_stale_after_days: int = 21
    job_recheck_after_hours: int = 24

    # --- Ingestion ---------------------------------------------------------
    ingest_user_agent: str = "job-app-board/0.1 (+https://github.com/srinashg/job-app-board)"
    ingest_request_timeout: float = 20.0
    playwright_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
