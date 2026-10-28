"""Resolve source revisions and persist advisory classifications atomically."""

from sqlalchemy import select

from apps.api.db import AuditRecord, ClassificationRecord, GenerationJob, NewsRecord
from packages.schemas.intelligence import ClassificationRequest
from services.market_data.event_store import (
    ImportConflict,
    aware,
    digest,
    latest_events,
    observation,
)
from services.news_intelligence.classification import parse_output, validate_evidence


def store_classification(
    session, request: ClassificationRequest, now, *, generation_owner=None, generation_metadata=None
):
    reserved = session.get(GenerationJob, request.classification_id)
    if reserved and reserved.status != "SUCCEEDED" and reserved.owner != generation_owner:
        raise ImportConflict("Classification ID is reserved by a generation job")
    checksum = digest(request.model_dump(mode="json"))
    existing = session.get(ClassificationRecord, request.classification_id)
    if existing:
        if existing.request_sha256 != checksum:
            raise ImportConflict("Classification ID reused with different input")
        return classification_view(existing) | {"duplicate": True}
    assessment = parse_output(request.raw_output)
    current_ids = {row.id for row in latest_events(session, "news", now)}
    sources = {}
    for source_id in assessment.source_ids:
        source = session.get(NewsRecord, source_id)
        if source is None or source_id not in current_ids:
            raise ValueError("Source must be an existing currently known news revision")
        sources[source_id] = observation(source)
    validate_evidence(assessment, sources)
    payload = {
        "request": request.model_dump(mode="json"),
        "assessment": assessment.model_dump(mode="json"),
        "source_snapshots": sources,
        "synthetic": any(source["synthetic"] for source in sources.values()),
    }
    if generation_metadata is not None:
        payload["generation"] = generation_metadata
    row = ClassificationRecord(
        id=request.classification_id, request_sha256=checksum, created_at=now, payload=payload
    )
    session.add(row)
    session.add(
        AuditRecord(
            action="news_classification_received", subject=request.classification_id, created_at=now
        )
    )
    session.flush()
    return classification_view(row) | {"duplicate": False}


def classification_view(row):
    return {
        "classification_id": row.id,
        "received_at": aware(row.created_at).isoformat(),
        "model_name": row.payload["request"]["model_name"],
        "model_version": row.payload["request"]["model_version"],
        "prompt_version": row.payload["request"]["prompt_version"],
        "synthetic": row.payload["synthetic"],
        "assessment": row.payload["assessment"],
        "advisory_only": True,
        "generation": row.payload.get("generation"),
    }


def classifications_as_of(session, as_of, symbol=None, limit=50):
    rows = session.scalars(
        select(ClassificationRecord)
        .where(ClassificationRecord.created_at <= as_of)
        .order_by(ClassificationRecord.created_at.desc(), ClassificationRecord.id)
    )
    return [
        classification_view(row)
        for row in rows
        if symbol is None or row.payload["assessment"]["symbol"] == symbol
    ][:limit]
