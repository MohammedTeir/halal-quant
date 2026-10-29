"""Explicit hypothetical control inputs; none establish real broker/reviewer authority."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from packages.schemas.data_events import AssetClass, Identifier, Provider, Symbol

Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=28, decimal_places=12)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=28, decimal_places=12)]
Fraction = Annotated[
    Decimal, Field(gt=0, le=1, allow_inf_nan=False, max_digits=12, decimal_places=10)
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ControlEvidence(Contract):
    evidence_id: Identifier
    provider: Provider
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: AwareDatetime
    recorded_at: AwareDatetime
    effective_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.observed_at > self.recorded_at or self.effective_at >= self.expires_at:
            raise ValueError("Invalid observation/recording or effective/expiry interval")
        return self


class AssetScreen(Contract):
    symbol: Symbol
    asset_class: AssetClass
    status: Literal["APPROVED", "PENDING", "REJECTED"] = "PENDING"
    methodology: Identifier
    evidence: ControlEvidence
    purification_guidance: str = Field(min_length=1, max_length=2000)
    business_activity_pass: StrictBool | None = None
    financial_ratios_pass: StrictBool | None = None
    fund_mandate_pass: StrictBool | None = None
    holdings_process_pass: StrictBool | None = None
    fund_structure_pass: StrictBool | None = None
    shariah_supervision_pass: StrictBool | None = None
    gold_ownership_pass: StrictBool | None = None
    gold_possession_pass: StrictBool | None = None
    gold_custody_pass: StrictBool | None = None
    gold_settlement_pass: StrictBool | None = None
    gold_redemption_pass: StrictBool | None = None

    @field_validator("purification_guidance")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Purification guidance must be explicit")
        return value


class InstrumentReview(Contract):
    symbol: Symbol
    asset_class: AssetClass
    kind: Literal["equity", "fund", "allocated_gold", "cfd", "future", "option", "unknown"]
    evidence: ControlEvidence
    settlement_and_possession_pass: StrictBool | None = None


class Position(Contract):
    symbol: Symbol
    asset_class: AssetClass
    sector: Identifier
    quantity: Nonnegative
    sellable_quantity: Nonnegative
    market_value: Nonnegative
    open_risk: Nonnegative | None = None

    @model_validator(mode="after")
    def sellable(self):
        if self.sellable_quantity > self.quantity:
            raise ValueError("Sellable quantity exceeds owned quantity")
        return self


class Reservation(Contract):
    reservation_id: Identifier
    symbol: Symbol
    sector: Identifier
    side: Literal["BUY", "SELL"]
    quantity: Positive
    notional: Nonnegative
    estimated_fee: Nonnegative
    planned_risk: Nonnegative | None = None


class AccountSnapshot(Contract):
    account_id: Identifier
    evidence: ControlEvidence
    connected: StrictBool = False
    account_type: Literal["cash", "margin", "unknown"] = "unknown"
    lending_enabled: StrictBool | None = None
    borrowing_enabled: StrictBool | None = None
    positions_complete: StrictBool = False
    reservations_complete: StrictBool = False
    equity: Positive
    day_start_equity: Positive
    peak_equity: Positive
    settled_cash: Nonnegative
    other_cash_holds: Nonnegative = Decimal(0)
    trading_day: date
    realized_pnl_today: Decimal = Decimal(0)
    consecutive_losses: int = Field(default=0, ge=0, strict=True)
    last_loss_at: AwareDatetime | None = None
    positions: tuple[Position, ...] = Field(default=(), max_length=500)
    reservations: tuple[Reservation, ...] = Field(default=(), max_length=500)

    @model_validator(mode="after")
    def consistent(self):
        if self.peak_equity < self.equity:
            raise ValueError("Peak equity cannot be below equity")
        if len({p.symbol for p in self.positions}) != len(self.positions):
            raise ValueError("Duplicate position symbols")
        if len({r.reservation_id for r in self.reservations}) != len(self.reservations):
            raise ValueError("Duplicate reservation IDs")
        if self.last_loss_at and self.last_loss_at > self.evidence.observed_at:
            raise ValueError("Last loss cannot be later than account observation")
        return self


class MarketQuote(Contract):
    symbol: Symbol
    asset_class: AssetClass
    evidence: ControlEvidence
    bid: Positive
    ask: Positive
    required_feeds_fresh: StrictBool = False

    @model_validator(mode="after")
    def spread(self):
        if self.bid > self.ask:
            raise ValueError("Bid exceeds ask")
        return self


class ControlPolicy(Contract):
    version: Identifier = "controls-research-v1"
    methodology: Identifier | None = None
    risk_per_trade: Fraction = Decimal("0.005")
    max_open_risk: Fraction = Decimal("0.03")
    max_position: Fraction = Decimal("0.10")
    max_sector: Fraction = Decimal("0.25")
    max_daily_loss: Fraction = Decimal("0.02")
    max_drawdown: Fraction = Decimal("0.10")
    consecutive_loss_limit: int = Field(default=3, gt=0, strict=True)
    cooldown_minutes: int = Field(default=60, gt=0, le=10080, strict=True)
    broker_max_age_seconds: int = Field(default=30, gt=0, le=86400, strict=True)
    quote_max_age_seconds: int = Field(default=15, gt=0, le=86400, strict=True)
    loss_day_timezone: str = "America/New_York"
    kill_switch: StrictBool = False
    fee_per_share: Nonnegative = Decimal(0)
    fee_per_order: Nonnegative = Decimal(0)
    slippage_bps: Decimal = Field(default=Decimal(0), ge=0, lt=10000)

    @field_validator("loss_day_timezone")
    @classmethod
    def timezone_known(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, KeyError) as error:
            raise ValueError("Unknown loss-day timezone") from error
        return value


class ControlCandidate(Contract):
    symbol: Symbol
    asset_class: AssetClass
    sector: Identifier
    action: Literal["BUY", "SELL", "SHORT"]
    quantity: Positive | None = None
    stop_price: Positive | None = None
    margin_requested: StrictBool = False
    borrow_requested: StrictBool = False


class ControlScenario(Contract):
    mode: Literal["hypothetical"] = "hypothetical"
    as_of: AwareDatetime
    candidate: ControlCandidate
    policy: ControlPolicy = Field(default_factory=ControlPolicy)
    assessment: AssetScreen | None = None
    instrument: InstrumentReview | None = None
    account: AccountSnapshot | None = None
    quote: MarketQuote | None = None
