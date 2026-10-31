"""Strict synthetic-only order contracts. No margin, borrowing or live mode."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from packages.schemas.controls import Contract, ControlPolicy, Positive
from packages.schemas.data_events import Identifier, Symbol

Quantity = Annotated[int, Field(strict=True, gt=0, le=1000000)]


class OpenAccount(Contract):
    account_id: Identifier
    mode: Literal["synthetic"] = "synthetic"
    initial_cash: Positive = Decimal(100000)
    universe: dict[Symbol, Identifier] = Field(min_length=1, max_length=100)
    policy: ControlPolicy = Field(default_factory=ControlPolicy)
    settlement_delay_seconds: int = Field(default=172800, ge=1, le=604800, strict=True)


class OrderRequest(Contract):
    command_id: Identifier
    symbol: Symbol
    side: Literal["BUY", "SELL"]
    quantity: Quantity
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: Positive | None = None
    stop_price: Positive | None = None
    expires_in_seconds: int = Field(default=3600, ge=1, le=86400, strict=True)

    @model_validator(mode="after")
    def order_fields(self):
        if (self.order_type == "LIMIT") != (self.limit_price is not None):
            raise ValueError("A limit order requires exactly one limit price")
        if self.side == "BUY" and self.stop_price is None:
            raise ValueError("Buy orders require a planned risk stop")
        return self


class QuoteRequest(Contract):
    command_id: Identifier
    symbol: Symbol
    source: Literal["synthetic"] = "synthetic"
    observed_at: AwareDatetime
    bid: Positive
    ask: Positive
    bid_size: Quantity
    ask_size: Quantity

    @model_validator(mode="after")
    def spread(self):
        if self.bid > self.ask:
            raise ValueError("Crossed quote")
        return self


class Command(Contract):
    command_id: Identifier


class FillRequest(Command):
    order_id: Identifier
    quote_id: Identifier


class CancelRequest(Command):
    order_id: Identifier


class HaltRequest(Command):
    engaged: StrictBool
    reason: str = Field(min_length=5, max_length=500)
