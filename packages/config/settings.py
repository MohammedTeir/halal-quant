from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://halal:halal@localhost:5432/halal_quant"
    dashboard_api_key: str = ""
    session_cookie_secure: bool = True
    session_hours: int = Field(default=12, ge=1, le=168)
    public_base_url: str = "https://localhost"
    telegram_bot_token: SecretStr = SecretStr("")
    tradingview_webhook_key: str = ""
    data_ingestion_key: str = ""
    analysis_api_key: str = ""
    controls_reviewer_key: str = ""
    controls_operator_key: str = ""
    controls_broker_key: str = ""
    controls_reviewer_identity: str | None = Field(default=None, max_length=200)
    controls_operator_identity: str | None = Field(default=None, max_length=200)
    alpaca_api_key: SecretStr = SecretStr("")
    alpaca_secret_key: SecretStr = SecretStr("")
    finnhub_api_key: SecretStr = SecretStr("")
    gemini_enabled: bool = False
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str | None = Field(
        default=None, max_length=128, pattern=r"^gemini-[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    gemini_timeout_seconds: float = Field(default=60, ge=0.1, le=120, allow_inf_nan=False)
    gemini_max_output_tokens: int = Field(default=4096, ge=512, le=8192)
    news_provider: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    calendar_provider: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    earnings_provider: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    fomc_provider: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    live_trading_enabled: bool = False

    @field_validator(
        "news_provider",
        "calendar_provider",
        "earnings_provider",
        "fomc_provider",
        "gemini_model",
        mode="before",
    )
    @classmethod
    def blank_provider_is_unconfigured(cls, value):
        return value or None

    @model_validator(mode="after")
    def research_only(self):
        if self.live_trading_enabled:
            raise ValueError("Live execution is not implemented; keep it disabled")
        keys = [
            key
            for key in (
                self.dashboard_api_key,
                self.tradingview_webhook_key,
                self.data_ingestion_key,
                self.analysis_api_key,
                self.controls_reviewer_key,
                self.controls_operator_key,
                self.controls_broker_key,
            )
            if key
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("All API credentials must be distinct")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
