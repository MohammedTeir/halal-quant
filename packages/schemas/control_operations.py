"""Role-separated reviewer attestations and server-owned control requests."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, HttpUrl, StrictBool, model_validator

from packages.schemas.controls import (
    AssetScreen,
    Contract,
    ControlEvidence,
    ControlPolicy,
    InstrumentReview,
    Nonnegative,
    Positive,
)
from packages.schemas.data_events import Identifier, Symbol


class ReviewerEvidence(Contract):
    note: str = Field(min_length=10, max_length=4000)
    references: tuple[HttpUrl, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def secure_references(self):
        if any(url.scheme != "https" or url.username or url.password for url in self.references):
            raise ValueError("Evidence references must be HTTPS without embedded credentials")
        return self


Threshold = Annotated[Decimal, Field(ge=0, le=1, max_digits=12, decimal_places=10)]


class MethodologyApproval(ReviewerEvidence):
    record_id: Identifier
    methodology_id: Identifier
    status: Literal["APPROVED", "PENDING", "REVOKED"] = "PENDING"
    evidence: ControlEvidence
    denominator: Literal["total_assets", "average_market_cap"]
    maximum_debt_ratio: Threshold
    maximum_interest_assets_ratio: Threshold
    maximum_impure_income_ratio: Threshold
    maximum_receivables_cash_ratio: Threshold | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    impure_income_boundary: Literal["strictly_below", "at_or_below"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    ratio_boundary: Literal["strictly_below", "at_or_below"]
    divestment_guidance: str = Field(min_length=10, max_length=4000)


class FinancialScreen(Contract):
    denominator: Literal["total_assets", "average_market_cap"]
    denominator_value: Positive
    debt: Nonnegative
    interest_assets: Nonnegative
    total_revenue: Positive
    impure_revenue: Nonnegative
    receivables_cash: Nonnegative | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def revenue(self):
        if self.impure_revenue > self.total_revenue:
            raise ValueError("Impure revenue exceeds revenue")
        return self


class AssetApproval(ReviewerEvidence):
    record_id: Identifier
    sector: Identifier
    assessment: AssetScreen
    instrument: InstrumentReview
    financials: FinancialScreen | None = None

    @model_validator(mode="after")
    def same_instrument(self):
        if (self.assessment.symbol, self.assessment.asset_class) != (
            self.instrument.symbol,
            self.instrument.asset_class,
        ):
            raise ValueError("Asset and instrument review scope mismatch")
        return self


class PolicyApproval(ReviewerEvidence):
    record_id: Identifier
    account_id: Identifier
    evidence: ControlEvidence
    policy: ControlPolicy

    @model_validator(mode="after")
    def version(self):
        if self.record_id != self.policy.version:
            raise ValueError("Policy version must equal immutable record ID")
        if self.policy.loss_day_timezone != "America/New_York":
            raise ValueError("Current broker activity adapter attests New York loss days only")
        return self


class RiskReconciliation(ReviewerEvidence):
    record_id: Identifier
    account_id: Identifier
    evidence: ControlEvidence
    trading_day: date
    day_start_equity: Positive
    peak_equity: Positive
    realized_pnl_today: Decimal = Field(max_digits=28, decimal_places=12)
    consecutive_losses: int = Field(ge=0, le=100000, strict=True)
    last_loss_at: AwareDatetime | None = None
    history_complete: StrictBool = False
    broker_activity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def loss_known(self):
        if self.last_loss_at and self.last_loss_at > self.evidence.observed_at:
            raise ValueError("Loss cannot follow reconciliation")
        return self


class KillSwitchChange(ReviewerEvidence):
    record_id: Identifier
    account_id: Identifier


class BrokerRefresh(Contract):
    refresh_id: Identifier


class QuoteRefresh(Contract):
    refresh_id: Identifier
    symbol: Symbol


class ControlCheck(Contract):
    check_id: Identifier
    account_id: Identifier
    signal_id: Identifier
    stop_price: Positive | None = None
    quantity: Positive | None = None
    reserve: StrictBool = True


class ReleaseReservation(Contract):
    release_id: Identifier
    reservation_id: Identifier
    reason: str = Field(min_length=10, max_length=1000)
