from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://halal:halal@localhost:5432/halal_quant"
    dashboard_api_key: str = ""
    tradingview_webhook_key: str = ""
    data_ingestion_key: str = ""
    analysis_api_key: str = ""
    alpaca_api_key: SecretStr = SecretStr("")
    alpaca_secret_key: SecretStr = SecretStr("")
    finnhub_api_key: SecretStr = SecretStr("")
    gemini_enabled: bool = False
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str | None = Field(
        default=None, max_length=128, pattern=r"^gemini-[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    gemini_timeout_seconds: float = Field(default=15, ge=0.1, le=20, allow_inf_nan=False)
    gemini_max_output_tokens: int = Field(default=4096, ge=512, le=8192)
    news_provider: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    calendar_provider: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    live_trading_enabled: bool = False

    @field_validator("news_provider", "calendar_provider", "gemini_model", mode="before")
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
            )
            if key
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("All API credentials must be distinct")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
