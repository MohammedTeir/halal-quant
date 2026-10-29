"""Claim → external inference → revalidate/persist. Retries never restart a claimed job."""

from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from apps.api.db import AuditRecord, ClassificationRecord, GenerationJob, NewsRecord
from packages.schemas.intelligence import ClassificationRequest, GenerationRequest
from services.market_data.event_store import (
    ImportConflict,
    aware,
    digest,
    latest_events,
    observation,
)
from services.news_intelligence.assessment_store import classification_view, store_classification
from services.news_intelligence.classification import (
    TARGET_PROMPT_VERSION,
    build_target_prompt,
    parse_output,
)
from services.news_intelligence.providers.gemini import GeminiAdapter, GeminiError


def job_view(row):
    return {
        "classification_id": row.id,
        "status": row.status,
        "created_at": aware(row.created_at).isoformat(),
        "completed_at": aware(row.completed_at).isoformat() if row.completed_at else None,
        "error_code": row.error_code,
        "configured_model": row.payload["configured_model"],
        "target": row.payload["request"],
        "result_metadata": row.result_metadata,
        "synthetic": row.payload["source"]["synthetic"],
        "advisory_only": True,
    }


def _claim(session, request, settings, now):
    checksum = digest(request.model_dump(mode="json"))
    existing = session.get(GenerationJob, request.classification_id)
    if existing:
        if existing.request_sha256 != checksum:
            raise ImportConflict("Generation ID reused with different target")
        if existing.status == "SUCCEEDED":
            classification = session.get(ClassificationRecord, existing.id)
            if classification is None:
                raise ImportConflict(
                    "Completed generation has no assessment; operator inspection required"
                )
            return None, classification_view(classification) | {"duplicate": True}
        raise ImportConflict(
            "Generation already running or previously failed; inspect job status before using a new ID"
        )
    if session.get(ClassificationRecord, request.classification_id):
        raise ImportConflict("Classification ID is already used by an imported assessment")
    if not settings.gemini_enabled:
        raise GeminiError("GEMINI_DISABLED")
    if not settings.gemini_model or not settings.gemini_api_key.get_secret_value():
        raise GeminiError("GEMINI_NOT_CONFIGURED")
    source = session.get(NewsRecord, request.source_id)
    current = {row.id for row in latest_events(session, "news", now)}
    if source is None or source.id not in current:
        raise ValueError("Generation requires an existing current news revision")
    snapshot = observation(source)
    symbols, classes = snapshot["symbols"], snapshot["asset_classes"]
    if (
        (symbols and request.symbol not in symbols)
        or (classes and request.asset_class not in classes)
        or (not symbols and request.asset_class not in classes)
    ):
        raise ValueError("Generation target is outside the source scope")
    owner = uuid4().hex
    payload = {
        "request": request.model_dump(mode="json"),
        "source": snapshot,
        "configured_model": settings.gemini_model,
        "prompt_version": TARGET_PROMPT_VERSION,
        "max_output_tokens": settings.gemini_max_output_tokens,
        "timeout_seconds": settings.gemini_timeout_seconds,
    }
    row = GenerationJob(
        id=request.classification_id,
        request_sha256=checksum,
        owner=owner,
        status="RUNNING",
        created_at=now,
        payload=payload,
    )
    session.add(row)
    session.add(AuditRecord(action="gemini_generation_started", subject=row.id, created_at=now))
    session.flush()
    return {"id": row.id, "owner": owner, "payload": payload}, None


def _fail(sessions, claim, code, now, metadata=None):
    with sessions.begin() as session:
        row = session.get(GenerationJob, claim["id"])
        if row and row.owner == claim["owner"] and row.status == "RUNNING":
            row.status, row.error_code, row.completed_at = "FAILED", code, now
            row.result_metadata = metadata
            session.add(
                AuditRecord(action="gemini_generation_failed", subject=row.id, created_at=now)
            )


def generate_classification(
    sessions, request: GenerationRequest, settings, clock, adapter_factory=GeminiAdapter
):
    # The claim is committed before inference. Race losers only inspect/replay it.
    for attempt in range(2):
        try:
            with sessions.begin() as session:
                claim, replay = _claim(session, request, settings, clock())
            break
        except IntegrityError:
            if attempt:
                raise ImportConflict("Concurrent generation claim conflict") from None
    if replay is not None:
        return replay
    target = {
        "event_id": request.source_id,
        "source_ids": [request.source_id],
        "symbol": request.symbol,
        "asset_class": request.asset_class,
    }
    prompt = build_target_prompt(
        [claim["payload"]["source"]], target, version=claim["payload"]["prompt_version"]
    )
    metadata = None
    try:
        completion = adapter_factory(settings).complete(prompt)
        metadata = {
            "provider": "gemini",
            "configured_model": claim["payload"]["configured_model"],
            "reported_model_version": completion.model_version,
            "usage": completion.usage,
        }
        assessment = parse_output(completion.text)
        if (
            assessment.event_id != request.source_id
            or assessment.source_ids != [request.source_id]
            or assessment.symbol != request.symbol
            or assessment.asset_class != request.asset_class
        ):
            raise ValueError("Model changed the requested classification target")
        stored = ClassificationRequest(
            classification_id=request.classification_id,
            model_name=f"gemini/{claim['payload']['configured_model']}",
            model_version=completion.model_version,
            prompt_version=claim["payload"]["prompt_version"],
            raw_output=completion.text,
        )
        with sessions.begin() as session:
            row = session.get(GenerationJob, request.classification_id)
            if row is None or row.owner != claim["owner"] or row.status != "RUNNING":
                raise ImportConflict("Generation claim no longer owned")
            # Resolve current source revisions AGAIN after the external call.
            result = store_classification(
                session,
                stored,
                clock(),
                generation_owner=claim["owner"],
                generation_metadata=metadata,
            )
            row.status, row.completed_at, row.result_metadata = "SUCCEEDED", clock(), metadata
            session.add(
                AuditRecord(
                    action="gemini_generation_succeeded", subject=row.id, created_at=clock()
                )
            )
        return result
    except GeminiError as error:
        _fail(sessions, claim, error.code, clock(), metadata)
        raise
    except (ValueError, ImportConflict):
        _fail(sessions, claim, "GEMINI_OUTPUT_INVALID", clock(), metadata)
        raise GeminiError("GEMINI_OUTPUT_INVALID") from None
    # An ambiguous process/DB failure deliberately leaves RUNNING. It is never
    # automatically regenerated; operators must inspect before a new paid attempt.
