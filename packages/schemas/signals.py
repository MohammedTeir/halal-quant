from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class AssetClass(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    GOLD = "gold"


class Signal(BaseModel):
    """Technical evidence only. This payload never authorizes an order."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:|/-]+$")
    strategy: Literal["adaptive_pullback", "regime_trend", "breakout_retest"]
    strategy_version: Literal["1.0.0"]
    asset_class: AssetClass
    symbol: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:/-]+$")
    timeframe: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    action: Literal["ENTRY_CANDIDATE", "EXIT_CANDIDATE"]
    bar_time: AwareDatetime
    price: Decimal = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def consistent_strategy(self):
        expected = {
            "adaptive_pullback": AssetClass.STOCK,
            "regime_trend": AssetClass.ETF,
            "breakout_retest": AssetClass.GOLD,
        }
        if self.asset_class != expected[self.strategy]:
            raise ValueError("Strategy does not match asset class")
        self.bar_time = self.bar_time.astimezone(UTC)
        return self

    def validate_delivery(self, now: datetime, maximum_age: timedelta) -> None:
        if self.bar_time > now + timedelta(seconds=30):
            raise ValueError("Future signal")
        if now - self.bar_time > maximum_age:
            raise ValueError("Stale signal")
