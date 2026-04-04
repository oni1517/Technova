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

    bolna_api_key: str | None = None
    bolna_api_url: str = "https://api.bolna.ai/call"
    bolna_agent_id: str | None = None
    bolna_from_phone_number: str | None = None
    bolna_default_recipient_phone_number: str | None = None
    bolna_provider: str = "vobiz"

    default_patient_lat: float = 18.5204
    default_patient_lon: float = 73.8567


def get_settings() -> Settings:
    return Settings()
