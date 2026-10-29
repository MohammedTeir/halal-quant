"""Facts and provenance, never AI classification or trade permissions."""

from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:/-]+$")]
Provider = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
Symbol = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:/-]+$")]
AssetClass = Literal["stock", "etf", "gold"]


class SourceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    provider: Provider
    item_id: Identifier
    revision: int = Field(default=1, ge=1, le=2147483647)
    synthetic: bool = False
    published_at: AwareDatetime

    @field_validator("published_at")
    @classmethod
    def utc_publication(cls, value):
        return value.astimezone(UTC)


class NewsEvent(SourceEvent):
    kind: Literal["news"] = "news"
    source_name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    headline: str = Field(min_length=1, max_length=1000)
    summary: str = Field(default="", max_length=20000)
    symbols: list[Symbol] = Field(default_factory=list, max_length=100)
    asset_classes: list[AssetClass] = Field(default_factory=list, max_length=3)

    @field_validator("url")
    @classmethod
    def safe_attribution_url(cls, value):
        parts = urlsplit(str(value))
        if parts.scheme != "https" or parts.username is not None or parts.password is not None:
            raise ValueError("Source URL must use HTTPS without embedded credentials")
        return value

    @field_validator("headline", "source_name")
    @classmethod
    def nonblank(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Text must not be blank")
        return value


class EconomicEvent(SourceEvent):
    kind: Literal["calendar"] = "calendar"
    title: str = Field(min_length=1, max_length=500)
    event_type: Literal["earnings", "fed", "cpi", "employment", "other"]
    scheduled_at: AwareDatetime
    severity: Literal["low", "medium", "high"]
    symbols: list[Symbol] = Field(default_factory=list, max_length=100)
    asset_classes: list[AssetClass] = Field(default_factory=list, max_length=3)
    cancelled: bool = False
    scheduled_precision: Literal["date"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    scheduled_timezone: str | None = Field(
        default=None, max_length=64, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def explicit_date_precision(self):
        if self.scheduled_precision is None and self.scheduled_timezone is None:
            return self
        if self.scheduled_precision != "date" or self.scheduled_timezone is None:
            raise ValueError("Date-only scheduling requires an explicit timezone")
        try:
            zone = ZoneInfo(self.scheduled_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown schedule timezone") from None
        if self.scheduled_at.astimezone(zone).time() != time.min:
            raise ValueError("Date-only timestamps must identify local midnight")
        return self

    # Omit absent metadata to preserve canonical payloads of existing imports.
    publication_basis: Literal["provider_timestamp", "observed_at"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @field_validator("scheduled_at")
    @classmethod
    def utc_schedule(cls, value):
        return value.astimezone(UTC)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Title must not be blank")
        return " ".join(value.split())


class CorporateAction(SourceEvent):
    kind: Literal["corporate_actions"] = "corporate_actions"
    publication_basis: Literal["provider_timestamp", "observed_at"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    symbol: Symbol
    action_type: Literal["split", "cash_dividend"]
    effective_at: AwareDatetime
    split_ratio: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    cash_amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    currency: Literal["USD"] = "USD"

    @field_validator("effective_at")
    @classmethod
    def utc_effective(cls, value):
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def action_fields(self):
        if self.action_type == "split":
            if self.split_ratio is None or self.cash_amount is not None or self.split_ratio == 1:
                raise ValueError("Split requires a non-unit new-shares/old-shares ratio only")
        elif self.cash_amount is None or self.split_ratio is not None:
            raise ValueError("Cash dividend requires a positive cash amount only")
        return self


Event = Annotated[NewsEvent | EconomicEvent | CorporateAction, Field(discriminator="kind")]


class FeedCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbols: list[Symbol] = Field(default_factory=list, max_length=100)
    asset_classes: list[AssetClass] = Field(min_length=1, max_length=3)
    purpose: Literal["company_news", "earnings", "macro_releases", "corporate_actions"]
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def utc_coverage(cls, value):
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_scope(self):
        if self.starts_at >= self.ends_at:
            raise ValueError("Coverage window must increase")
        if not self.symbols and self.purpose != "macro_releases":
            raise ValueError("Only macro releases may declare an all-symbol scope")
        if len(set(self.symbols)) != len(self.symbols) or len(set(self.asset_classes)) != len(
            self.asset_classes
        ):
            raise ValueError("Coverage scopes must be unique")
        return self


class DataBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Provider
    kind: Literal["news", "calendar", "corporate_actions"]
    batch_id: Identifier
    synthetic: bool = False
    records: list[Event] = Field(default_factory=list, max_length=100)
    coverage: FeedCoverage | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def uniform_source(self):
        if self.coverage is not None:
            expected_kind = {
                "company_news": "news",
                "earnings": "calendar",
                "macro_releases": "calendar",
                "corporate_actions": "corporate_actions",
            }[self.coverage.purpose]
            if self.kind != expected_kind:
                raise ValueError("Coverage purpose does not match source kind")
            for record in self.records:
                if record.kind == "news":
                    stamp = record.published_at
                    symbols = record.symbols
                    classes = record.asset_classes
                elif record.kind == "calendar":
                    if (self.coverage.purpose == "earnings") != (record.event_type == "earnings"):
                        raise ValueError("Calendar coverage purpose does not match event type")
                    stamp = record.scheduled_at
                    symbols = record.symbols
                    classes = record.asset_classes
                else:
                    stamp = record.effective_at
                    symbols, classes = [record.symbol], []
                if (
                    not self.coverage.starts_at <= stamp <= self.coverage.ends_at
                    or (
                        self.coverage.symbols
                        and (not symbols or not set(symbols) <= set(self.coverage.symbols))
                    )
                    or (classes and not set(classes) <= set(self.coverage.asset_classes))
                ):
                    raise ValueError("Event is outside declared poll coverage")
        if any(
            record.provider != self.provider
            or record.kind != self.kind
            or record.synthetic != self.synthetic
            for record in self.records
        ):
            raise ValueError("All records must match batch provider, kind and synthetic label")
        identities = [(record.item_id, record.revision) for record in self.records]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate item/revision inside batch")
        return self


class ActionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: CorporateAction
    received_at: AwareDatetime

    @field_validator("received_at")
    @classmethod
    def utc_received(cls, value: datetime):
        return value.astimezone(UTC)
