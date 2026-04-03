from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Golden Hour Emergency Triage & Routing System"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    database_url: str | None = None

    anthropic_api_key: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_model: str = "claude-sonnet-4-20250514"

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    twilio_to_number: str | None = None

    default_patient_lat: float = 18.5204
    default_patient_lon: float = 73.8567

    eta_weight: float = 0.65
    bed_weight: float = 0.25
    department_weight: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()

