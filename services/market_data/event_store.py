"""Atomic imports and causal, immutable source observations."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from apps.api.db import AuditRecord, CorporateActionRecord, DataImport, EconomicRecord, NewsRecord
from packages.schemas.data_events import DataBatch
from services.news_intelligence.normalization import canonical_url

TABLES = {
    "news": NewsRecord,
    "calendar": EconomicRecord,
    "corporate_actions": CorporateActionRecord,
}


class ImportConflict(ValueError):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def aware(value):
    # SQLite loses timezone metadata; this adapter's DB timestamps are always stored in UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def check_as_of(value: datetime, now: datetime):
    if value.tzinfo is None or value > now:
        raise ValueError("as_of must be timezone-aware and cannot be in the future")
    return value.astimezone(UTC)


def import_batch(session, batch: DataBatch, now: datetime):
    if now.tzinfo is None:
        raise ValueError("Server clock must be timezone-aware")
    now = now.astimezone(UTC)
    identity = digest([batch.provider, batch.kind, batch.batch_id])
    checksum = digest(batch.model_dump(mode="json"))
    previous = session.get(DataImport, identity)
    if previous:
        if previous.payload_sha256 != checksum:
            raise ImportConflict("Batch ID reused with different content")
        return {
            "batch_id": previous.batch_id,
            "duplicate": True,
            "inserted": previous.inserted,
            "duplicates": previous.duplicates,
            "received_at": aware(previous.received_at).isoformat(),
        }
    table = TABLES[batch.kind]
    inserted, duplicates = 0, 0
    # Validate everything before mutating the session: an invalid record cannot refresh a feed.
    pending = []
    for event in batch.records:
        if event.published_at > now:
            raise ValueError("Source publication cannot be later than server receipt")
        payload = event.model_dump(mode="json")
        record_id = digest([event.provider, event.item_id, event.revision])
        existing = session.get(table, record_id)
        if existing:
            if existing.payload != payload:
                raise ImportConflict("Source revision is immutable; use a new revision")
            duplicates += 1
            continue
        values = {
            "id": record_id,
            "provider": event.provider,
            "item_id": event.item_id,
            "revision": event.revision,
            "published_at": event.published_at,
            "received_at": now,
            "payload": payload,
        }
        if batch.kind == "news":
            values["story_key"] = digest(canonical_url(event.url))
        pending.append(table(**values))
        inserted += 1
    session.add_all(pending)
    session.add(
        DataImport(
            id=identity,
            provider=batch.provider,
            kind=batch.kind,
            batch_id=batch.batch_id,
            synthetic=batch.synthetic,
            payload_sha256=checksum,
            received_at=now,
            inserted=inserted,
            duplicates=duplicates,
        )
    )
    session.add(AuditRecord(action=f"data_import_{batch.kind}", subject=identity, created_at=now))
    session.flush()
    return {
        "batch_id": batch.batch_id,
        "duplicate": False,
        "inserted": inserted,
        "duplicates": duplicates,
        "received_at": now.isoformat(),
    }


def latest_events(session, kind, as_of, provider=None):
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    table = TABLES[kind]
    statement = select(table).where(table.published_at <= as_of, table.received_at <= as_of)
    if provider is not None:
        statement = statement.where(table.provider == provider)
    rows = session.scalars(statement)
    latest = {}
    for row in rows:
        key = (row.provider, row.item_id)
        if key not in latest or latest[key].revision < row.revision:
            latest[key] = row
    return sorted(
        latest.values(), key=lambda r: (aware(r.published_at), r.provider, r.item_id), reverse=True
    )


def observation(row):
    return row.payload | {"received_at": aware(row.received_at).isoformat()}


def relevant(payload, symbol=None, asset_class=None):
    return (symbol is None or symbol in payload.get("symbols", [])) and (
        asset_class is None or asset_class in payload.get("asset_classes", [])
    )


def feed_status(session, provider, kind, as_of, maximum_age=timedelta(minutes=15)):
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if maximum_age <= timedelta(0):
        raise ValueError("Maximum age must be positive")
    latest = session.scalar(
        select(DataImport)
        .where(
            DataImport.provider == provider,
            DataImport.kind == kind,
            DataImport.received_at <= as_of,
        )
        .order_by(DataImport.received_at.desc(), DataImport.id)
        .limit(1)
    )
    age = (as_of - aware(latest.received_at)).total_seconds() if latest else None
    fresh = age is not None and 0 <= age <= maximum_age.total_seconds()
    return {
        "provider": provider,
        "kind": kind,
        "as_of": as_of.isoformat(),
        "state": "FRESH" if fresh else "STALE" if latest else "MISSING",
        "last_successful_at": aware(latest.received_at).isoformat() if latest else None,
        "age_seconds": age,
        "required_feed_available": fresh and not latest.synthetic,
        "synthetic": latest.synthetic if latest else None,
        "provider_independently_verified": False,
        "authorized_for_entry": False,
    }
