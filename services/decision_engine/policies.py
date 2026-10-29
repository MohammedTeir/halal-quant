"""Entry restrictions from known facts and validated assessments; never permission."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from packages.schemas.intelligence import Assessment


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    version: str = "decision-v1"
    minimum_score: float = Field(default=0.65, ge=0, le=1)
    minimum_confidence: float = Field(default=0.7, ge=0, le=1)
    minimum_relevance: float = Field(default=0.5, ge=0, le=1)
    earnings_before_hours: int = Field(default=24, ge=0)
    earnings_after_hours: int = Field(default=24, ge=0)
    macro_before_hours: int = Field(default=2, ge=0)
    macro_after_hours: int = Field(default=1, ge=0)
    news_lookback_hours: int = Field(default=24, ge=1)
    assessment_age_minutes: int = Field(default=60, ge=1)
    feed_age_minutes: int = Field(default=15, ge=1)


def calendar_restrictions(
    events: list[dict], symbol: str, asset_class: str, as_of: datetime, policy: DecisionPolicy
):
    if as_of.tzinfo is None:
        raise ValueError("Calendar evaluation requires an aware time")
    reasons = []
    for event in events:
        if event["cancelled"]:
            continue
        symbols, classes = event.get("symbols", []), event.get("asset_classes", [])
        specific = symbol in symbols
        scoped = specific or asset_class in classes
        unknown_scope = not symbols and not classes
        earnings = event["event_type"] == "earnings"
        unknown_earnings_scope = (
            earnings and not symbols and (asset_class in classes or not classes)
        )
        if earnings:
            if asset_class != "stock" or (not specific and not unknown_earnings_scope):
                continue
            before, after = policy.earnings_before_hours, policy.earnings_after_hours
        else:
            if event["severity"] != "high" or not (scoped or unknown_scope):
                continue
            before, after = policy.macro_before_hours, policy.macro_after_hours
        scheduled = datetime.fromisoformat(event["scheduled_at"])
        start, end = scheduled, scheduled
        if event.get("scheduled_precision") == "date":
            start = scheduled.astimezone(ZoneInfo(event["scheduled_timezone"]))
            end = start + timedelta(days=1)
        window_start = start - timedelta(hours=before)
        window_end = end + timedelta(hours=after)
        if window_start <= as_of <= window_end:
            reasons.append(
                {
                    "code": "EVENT_SCOPE_REVIEW"
                    if unknown_scope or unknown_earnings_scope
                    else "EARNINGS_WINDOW"
                    if earnings
                    else "HIGH_IMPACT_WINDOW",
                    "source_id": event["source_id"],
                    "event_type": event["event_type"],
                    "scheduled_at": scheduled.isoformat(),
                    "synthetic": event["synthetic"],
                }
            )
    return sorted(reasons, key=lambda reason: (reason["scheduled_at"], reason["source_id"]))


def assessment_restrictions(assessment: Assessment, policy: DecisionPolicy):
    reasons = []
    if assessment.requires_human_review or assessment.recommended_policy != "ALLOW":
        reasons.append(
            "MODEL_RESTRICT" if assessment.recommended_policy == "RESTRICT" else "MODEL_REVIEW"
        )
    if assessment.confidence < policy.minimum_confidence:
        reasons.append("LOW_CONFIDENCE")
    if assessment.relevance < policy.minimum_relevance:
        reasons.append("UNCERTAIN_RELEVANCE")
    if (
        assessment.sentiment == "negative"
        and assessment.severity == "high"
        and assessment.relevance >= policy.minimum_relevance
    ):
        reasons.append("ADVERSE_HIGH_SEVERITY_NEWS")
    if assessment.market_impact == "uncertain":
        reasons.append("MARKET_IMPACT_UNCERTAIN")
    if assessment.sentiment == "mixed":
        reasons.append("CONFLICTING_NEWS")
    return reasons
