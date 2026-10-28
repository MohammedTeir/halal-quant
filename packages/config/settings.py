from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://halal:halal@localhost:5432/halal_quant"
    dashboard_api_key: str = ""
    tradingview_webhook_key: str = ""
    live_trading_enabled: bool = False

    @model_validator(mode="after")
    def research_only(self):
        if self.live_trading_enabled:
            raise ValueError("Live execution is not implemented; keep it disabled")
        if self.dashboard_api_key and self.dashboard_api_key == self.tradingview_webhook_key:
            raise ValueError("Dashboard and webhook credentials must be distinct")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
