"""Preview or generate one grounded news assessment; never approves or trades.

An existing job ID is inspected without another model call, even after failure.
The shared Gemini adapter retains its bounded HTTP retry policy for a new job.
"""

import argparse
import json
from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError

from apps.api.db import ClassificationRecord, GenerationJob, session_factory, utcnow
from packages.config.settings import get_settings
from packages.schemas.intelligence import GenerationRequest
from services.market_data.event_store import ImportConflict, aware, latest_events
from services.news_intelligence.generation import generate_classification
from services.news_intelligence.providers.gemini import GeminiError


def classify_one(
    sessions,
    settings,
    *,
    symbol,
    classification_id,
    generate=False,
    clock=utcnow,
    generator=generate_classification,
):
    # Validate identifiers before any database operation, without printing input errors.
    target = GenerationRequest(
        classification_id=classification_id, source_id="0" * 64, symbol=symbol, asset_class="stock"
    )
    result = {
        "classification_id": target.classification_id,
        "symbol": target.symbol,
        "advisory_only": True,
        "authorized": False,
        "orders_submitted": 0,
        "messages_sent": 0,
    }
    now = clock()
    with sessions() as db:
        old = db.get(GenerationJob, classification_id)
        if old is not None:
            if (old.payload["request"]["symbol"], old.payload["request"]["asset_class"]) != (
                symbol,
                "stock",
            ):
                return result | {"status": "CLASSIFICATION_ID_TARGET_MISMATCH"}
            if (
                old.status == "SUCCEEDED"
                and db.get(ClassificationRecord, classification_id) is None
            ):
                return result | {"status": "JOB_LEDGER_INCONSISTENT"}
            return result | {
                "status": old.status,
                "existing_job": True,
                "error_code": old.error_code,
                "new_generation_requested": False,
            }
        if db.get(ClassificationRecord, classification_id) is not None:
            return result | {"status": "CLASSIFICATION_ID_ALREADY_USED"}
        source = next(
            (
                row
                for row in latest_events(db, "news", now, "finnhub")
                if row.payload.get("synthetic") is False
                and symbol in row.payload.get("symbols", [])
                and "stock" in row.payload.get("asset_classes", [])
                and now - timedelta(hours=24) <= aware(row.published_at)
                and now - timedelta(hours=24) <= aware(row.received_at)
            ),
            None,
        )
        if source is None:
            return result | {"status": "RECENT_NON_SYNTHETIC_COMPANY_NEWS_REQUIRED"}
        request = target.model_copy(update={"source_id": source.id})
    result |= {"source_id": request.source_id, "model": settings.gemini_model}
    if not settings.gemini_enabled or not (
        settings.gemini_model and settings.gemini_api_key.get_secret_value()
    ):
        return result | {"status": "GEMINI_CONFIGURATION_REQUIRED"}
    if not generate:
        return result | {"status": "READY_FOR_GENERATION", "new_generation_requested": False}
    try:
        stored = generator(sessions, request, settings, clock)
    except GeminiError as error:
        return result | {"status": "GENERATION_FAILED", "error_code": error.code}
    except ImportConflict:
        return result | {"status": "JOB_CONFLICT_INSPECT_BEFORE_RETRY"}
    assessment = stored["assessment"]
    return result | {
        "status": "SUCCEEDED",
        "new_generation_requested": True,
        "assessment": {
            name: assessment[name]
            for name in (
                "event_type",
                "sentiment",
                "confidence",
                "recommended_policy",
                "requires_human_review",
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--classification-id", required=True)
    parser.add_argument(
        "--generate", action="store_true", help="Start one new job using your Google account quota"
    )
    args = parser.parse_args()
    engine = None
    try:
        settings = get_settings()
        if "database_url" not in settings.model_fields_set:
            result = {"status": "DATABASE_URL_NOT_CONFIGURED"}
        else:
            engine, sessions = session_factory(settings.database_url)
            result = classify_one(
                sessions,
                settings,
                symbol=args.symbol,
                classification_id=args.classification_id,
                generate=args.generate,
            )
    except (ValueError, SQLAlchemyError, OSError):
        result = {
            "status": "PRIVATE_CONFIGURATION_OR_DATABASE_UNAVAILABLE",
            "classification_id": args.classification_id,
            "inspect_existing_job_before_retry": True,
        }
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
