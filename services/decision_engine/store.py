"""Build trusted state on the server; clients cannot supply compliance or risk approvals."""

from datetime import timedelta

from sqlalchemy import select

from apps.api.db import AuditRecord, ClassificationRecord, DecisionRecord, SignalRecord
from packages.schemas.intelligence import Assessment, EvaluationRequest
from packages.schemas.signals import Signal
from services.decision_engine.engine import TrustedState, evaluate
from services.decision_engine.policies import (
    DecisionPolicy,
    assessment_restrictions,
    calendar_restrictions,
)
from services.market_data.event_store import (
    ImportConflict,
    aware,
    check_as_of,
    digest,
    feed_status,
    latest_events,
    observation,
)


def _scope(payload, symbol, asset_class):
    return (
        symbol in payload["symbols"]
        if payload["symbols"]
        else asset_class in payload["asset_classes"]
    )


def _feed(session, provider, kind, as_of, policy):
    if provider is None:
        return {
            "provider": None,
            "kind": kind,
            "state": "UNCONFIGURED",
            "required_feed_available": False,
            "provider_independently_verified": False,
            "authorized_for_entry": False,
        }
    return feed_status(session, provider, kind, as_of, timedelta(minutes=policy.feed_age_minutes))


def intelligence_snapshot(session, signal, as_of, settings, policy):
    news_feed = _feed(session, settings.news_provider, "news", as_of, policy)
    calendar_feed = _feed(session, settings.calendar_provider, "calendar", as_of, policy)
    articles = [
        row
        for row in latest_events(session, "news", as_of, settings.news_provider)
        if settings.news_provider is not None
        and _scope(row.payload, signal.symbol, signal.asset_class)
        and aware(row.published_at) >= as_of - timedelta(hours=policy.news_lookback_hours)
    ]
    calendar = [
        observation(row)
        for row in latest_events(session, "calendar", as_of, settings.calendar_provider)
        if settings.calendar_provider is not None
    ]
    windows = calendar_restrictions(calendar, signal.symbol, signal.asset_class, as_of, policy)
    active_ids = {row.id for row in latest_events(session, "news", as_of)}
    article_ids = {row.id for row in articles}
    classifications = session.scalars(
        select(ClassificationRecord)
        .where(
            ClassificationRecord.created_at <= as_of,
            ClassificationRecord.created_at
            >= as_of - timedelta(minutes=policy.assessment_age_minutes),
        )
        .order_by(ClassificationRecord.created_at, ClassificationRecord.id)
    )
    covered, reviews = set(), []
    considered = []
    for row in classifications:
        assessment = Assessment.model_validate(row.payload["assessment"])
        if (
            assessment.symbol != signal.symbol
            or assessment.asset_class != signal.asset_class
            or assessment.event_id not in article_ids
            or not set(assessment.source_ids) <= active_ids
        ):
            continue
        covered.update(set(assessment.source_ids) & article_ids)
        considered.append(
            {
                "classification_id": row.id,
                "created_at": aware(row.created_at).isoformat(),
                "model_name": row.payload["request"]["model_name"],
                "model_version": row.payload["request"]["model_version"],
                "prompt_version": row.payload["request"]["prompt_version"],
                "assessment": assessment.model_dump(mode="json"),
            }
        )
        reviews.extend(
            {"code": reason, "classification_id": row.id}
            for reason in assessment_restrictions(assessment, policy)
        )
    sentiments = {item["assessment"]["sentiment"] for item in considered}
    if {"positive", "negative"} <= sentiments:
        reviews.append(
            {
                "code": "CONFLICTING_ASSESSMENTS",
                "classification_ids": [item["classification_id"] for item in considered],
            }
        )
    # Positive advisory text never clears source-verification, missing-feed or calendar gates.
    blockers = []
    for name, feed in (("news", news_feed), ("calendar", calendar_feed)):
        if not feed["required_feed_available"]:
            blockers.append(
                {"code": "REQUIRED_FEED_UNAVAILABLE", "kind": name, "state": feed["state"]}
            )
        if not feed["provider_independently_verified"]:
            blockers.append({"code": "PROVIDER_UNVERIFIED", "kind": name})
    missing = sorted(article_ids - covered)
    if missing:
        blockers.append({"code": "UNCLASSIFIED_NEWS", "source_ids": missing})
    return {
        "allows_entry": not (blockers or windows or reviews),
        "feed_blockers": blockers,
        "feeds": {"news": news_feed, "calendar": calendar_feed},
        "event_restrictions": windows,
        "assessment_restrictions": reviews,
        "classifications": considered,
        "news_source_ids": sorted(article_ids),
        "calendar_snapshot": calendar,
    }


def store_evaluation(session, request: EvaluationRequest, now, settings):
    checksum = digest(request.model_dump(mode="json"))
    existing = session.get(DecisionRecord, request.evaluation_id)
    if existing:
        if existing.request_sha256 != checksum:
            raise ImportConflict("Evaluation ID reused with different input")
        return existing.response | {"duplicate": True}
    as_of = check_as_of(request.as_of or now, now)
    record = session.get(SignalRecord, request.signal_id)
    if record is None or aware(record.received_at) > as_of:
        raise ValueError("Signal must already be known at the evaluation time")
    signal = Signal.model_validate(record.payload)
    if signal.bar_time > as_of:
        raise ValueError("Signal bar cannot be later than the evaluation time")
    policy = DecisionPolicy()
    intelligence = intelligence_snapshot(session, signal, as_of, settings, policy)
    fresh_signal = as_of - signal.bar_time <= timedelta(minutes=15)
    # These authorities do not exist yet. Do not promote webhook prices, imported
    # text, model claims or caller-supplied flags into broker/compliance evidence.
    state = TrustedState(data_is_fresh=False, news_allows_entry=intelligence["allows_entry"])
    result = evaluate(signal.action, request.score, state, policy)
    response = result | {
        "evaluation_id": request.evaluation_id,
        "duplicate": False,
        "as_of": as_of.isoformat(),
        "recorded_at": now.isoformat(),
        "snapshot": {
            "signal": record.payload,
            "signal_received_at": aware(record.received_at).isoformat(),
            "signal_is_fresh": fresh_signal,
            "score": request.score,
            "policy": policy.model_dump(),
            "intelligence": intelligence,
            "trusted_state": state.model_dump(mode="json"),
            "unavailable_authorities": [
                "verified_market_data",
                "broker",
                "asset_compliance",
                "instrument_review",
                "portfolio_risk",
                "ownership",
            ],
        },
    }
    session.add(
        DecisionRecord(
            id=request.evaluation_id,
            request_sha256=checksum,
            signal_id=request.signal_id,
            created_at=now,
            response=response,
        )
    )
    session.add(
        AuditRecord(action="candidate_evaluated", subject=request.evaluation_id, created_at=now)
    )
    session.flush()
    return response
