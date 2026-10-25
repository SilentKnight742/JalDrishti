"""Environment-backed API configuration."""

from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="JALDRISHTI_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "JalDrishti API"
    service_id: str = "jaldrishti-api"
    version: str = "0.1.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://jaldrishti:jaldrishti@postgres:5432/jaldrishti"
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    healthcheck_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    incident_rate_limit_per_hour: int = Field(default=10, ge=1, le=1_000)
    incident_media_max_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    incident_media_directory: str = "/var/lib/jaldrishti/incidents"
    contact_encryption_key: str = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    contact_encryption_key_id: str = "development-only-v1"

    @model_validator(mode="after")
    def validate_contact_encryption(self) -> "Settings":
        try:
            Fernet(self.contact_encryption_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise ValueError("contact_encryption_key must be a valid Fernet key") from exc
        if self.environment.lower() not in {"development", "test", "local"} and (
            self.contact_encryption_key_id == "development-only-v1"
            or self.contact_encryption_key == "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
        ):
            raise ValueError("replace the development incident contact encryption key")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings object for the process."""

    return Settings()
