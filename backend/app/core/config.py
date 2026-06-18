"""12-factor configuration via environment variables (Pydantic v2 settings).

Every tunable lives here; nothing is hard-coded in business logic. Import the
singleton ``settings`` everywhere::

    from app.core.config import settings
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- General ----
    environment: str = "local"
    log_level: str = "INFO"
    tz: str = "Africa/Nairobi"

    # ---- Database ----
    database_url: str = "postgresql+asyncpg://angawatch:angawatch@localhost:5432/angawatch"
    database_url_sync: str = "postgresql+psycopg://angawatch:angawatch@localhost:5432/angawatch"
    db_echo: bool = False

    # ---- Redis / Celery ----
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ---- MQTT ----
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_telemetry_topic: str = "farm/+/+/telemetry"
    mqtt_client_id: str = "angawatch-ingestion"

    # ---- Auth / security ----
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    secret_key: str = "change-me"

    # ---- API ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # ---- Risk engine / scheduling ----
    risk_eval_interval_minutes: int = 10
    weather_poll_interval_minutes: int = 30

    # ---- Alerting ----
    alerting_default_channel: str = "console"
    at_username: str = "sandbox"
    at_api_key: str | None = None
    at_sender_id: str = "ANGAWATCH"
    at_use_sandbox: bool = True

    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_api_version: str = "v21.0"
    whatsapp_verify_token: str = "angawatch-verify"

    # ---- M-Pesa ----
    mpesa_environment: str = "sandbox"
    mpesa_consumer_key: str | None = None
    mpesa_consumer_secret: str | None = None
    mpesa_shortcode: str = "174379"
    mpesa_passkey: str = ""
    mpesa_callback_base_url: str = "https://example.ngrok.io"
    mpesa_transaction_type: str = "CustomerPayBillOnline"

    # ---- Weather ----
    weather_provider: str = "mock"
    openweather_api_key: str | None = None
    tomorrowio_api_key: str | None = None

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
