"""An untrusted analytical contract. No holdings, permissions or execution fields."""

from datetime import UTC
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

from packages.schemas.data_events import AssetClass, Identifier, Symbol

SourceId = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Quote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2000)]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: SourceId
    quote: Quote


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal["1.0"]
    event_id: SourceId
    symbol: Symbol
    asset_class: AssetClass
    event_type: Literal["earnings", "company", "fed", "cpi", "employment", "other"]
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    sentiment_score: float = Field(ge=-1, le=1, strict=True)
    relevance: float = Field(ge=0, le=1, strict=True)
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1, strict=True)
    source_ids: list[SourceId] = Field(min_length=1, max_length=20)
    evidence: list[Evidence] = Field(min_length=1, max_length=40)
    market_impact: Literal["positive", "negative", "neutral", "uncertain"]
    recommended_policy: Literal["ALLOW", "REVIEW", "RESTRICT"]
    requires_human_review: StrictBool

    @model_validator(mode="after")
    def consistent_citations(self):
        ids = set(self.source_ids)
        if len(ids) != len(self.source_ids) or self.event_id not in ids:
            raise ValueError("Source IDs must be unique and include the anchor event")
        if {e.source_id for e in self.evidence} != ids:
            raise ValueError(
                "Every declared source must have evidence and no undeclared source may be cited"
            )
        if (
            self.sentiment == "positive"
            and self.sentiment_score <= 0
            or self.sentiment == "negative"
            and self.sentiment_score >= 0
            or self.sentiment == "neutral"
            and self.sentiment_score != 0
        ):
            raise ValueError("Sentiment and numerical score disagree")
        return self


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    classification_id: Identifier
    model_name: Identifier
    model_version: Identifier
    prompt_version: Literal[
        "news-classification-v1",
        "news-classification-v2",
        "news-classification-v3",
        "news-classification-v4",
        "news-classification-v5",
    ]
    raw_output: str = Field(min_length=2, max_length=65536)


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    evaluation_id: Identifier
    signal_id: Identifier
    score: float = Field(ge=0, le=1, strict=True)
    as_of: AwareDatetime | None = None

    @field_validator("as_of")
    @classmethod
    def utc_cutoff(cls, value):
        return value.astimezone(UTC) if value else None


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    classification_id: Identifier
    source_id: SourceId
    symbol: Symbol
    asset_class: AssetClass
