"""Strict internal simulation contracts. No margin, borrowing or live transport."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from packages.schemas.controls import Contract, ControlPolicy, Positive
from packages.schemas.data_events import Identifier, Symbol

Quantity = Annotated[int, Field(strict=True, gt=0, le=1000000)]
AccountId = Annotated[
    str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
]


class OpenAccount(Contract):
    account_id: AccountId
    mode: Literal["synthetic", "forward"] = "synthetic"
    initial_cash: Positive = Decimal(100000)
    universe: dict[Symbol, Identifier] = Field(min_length=1, max_length=100)
    provider_symbols: dict[Symbol, str] = Field(
        default_factory=dict, max_length=100, exclude_if=lambda value: not value
    )
    asset_classes: dict[Symbol, Literal["stock", "etf"]] = Field(
        default_factory=dict, max_length=100, exclude_if=lambda value: not value
    )
    settlement_days: int = Field(
        default=1, ge=1, le=3, strict=True, exclude_if=lambda value: value == 1
    )
    policy: ControlPolicy = Field(default_factory=ControlPolicy)
    settlement_delay_seconds: int = Field(default=172800, ge=1, le=604800, strict=True)

    @model_validator(mode="after")
    def universe_scope(self):
        import re

        if set(self.asset_classes) - set(self.universe) or set(self.provider_symbols) - set(
            self.universe
        ):
            raise ValueError("Asset/provider mappings must belong to the account universe")
        if self.mode == "forward":
            values = [self.provider_symbols.get(k, k) for k in self.universe]
            if (
                len(values) > 10
                or len(set(values)) != len(values)
                or any(not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", value) for value in values)
            ):
                raise ValueError("Forward accounts need 1-10 distinct explicit US ticker mappings")
        return self


class OrderRequest(Contract):
    command_id: Identifier
    symbol: Symbol
    side: Literal["BUY", "SELL"]
    quantity: Quantity
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: Positive | None = None
    stop_price: Positive | None = None
    decision_id: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)
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
    source: Literal["synthetic", "alpaca_iex"] = "synthetic"
    observed_at: AwareDatetime
    bid: Positive
    ask: Positive
    receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$", exclude_if=lambda value: value is None
    )
    session_open: AwareDatetime | None = Field(default=None, exclude_if=lambda value: value is None)
    session_close: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    settlement_at: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
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


class ForwardProtocol(Contract):
    run_id: AccountId
    account_id: AccountId
    provider: Literal["alpaca_iex"] = "alpaca_iex"
    minimum_sessions: int = Field(default=20, ge=20, le=100, strict=True)
    minimum_round_trips: int = Field(default=10, ge=3, le=10000, strict=True)
    maximum_gap_seconds: int = Field(default=180, ge=60, le=300, strict=True)
    cadence_seconds: int = Field(default=60, ge=15, le=120, strict=True)
    quantity_per_decision: Quantity = 1
    stop_fraction: Decimal = Field(
        default=Decimal("0.05"), gt=0, lt=1, max_digits=12, decimal_places=10
    )
    feed_providers: dict[
        Literal["news", "calendar", "fomc", "earnings", "corporate_actions"], Identifier
    ] = Field(min_length=5, max_length=5)
    decision_max_age_seconds: int = Field(default=300, ge=1, le=900, strict=True)
    data_review: dict[str, str] = Field(min_length=1, max_length=10)
    source_limitations: str = Field(min_length=20, max_length=4000)
    references: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def references_secure(self):
        from urllib.parse import urlsplit

        for value in self.references:
            parts = urlsplit(value)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                raise ValueError("Use HTTPS evidence references without credentials")
        if self.cadence_seconds * 2 > self.maximum_gap_seconds:
            raise ValueError("Allow at least two polling intervals per maximum gap")
        return self


class ReviewRun(Contract):
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: StrictBool
    expires_at: AwareDatetime
    note: str = Field(min_length=20, max_length=4000)


class DecisionOrder(Contract):
    decision_id: Identifier
    quantity: Quantity
    stop_price: Positive | None = None


class ExitRequest(Command):
    reason: str = Field(min_length=5, max_length=500)
