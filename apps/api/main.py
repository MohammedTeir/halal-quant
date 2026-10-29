import hmac
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.api.db import (
    AuditRecord,
    ClassificationRecord,
    CorporateActionRecord,
    DataImport,
    DecisionRecord,
    EconomicRecord,
    FeedCoverageRecord,
    GenerationJob,
    NewsRecord,
    SignalRecord,
    session_factory,
    utcnow,
)
from packages.config.settings import Settings, get_settings
from packages.schemas.controls import ControlScenario
from packages.schemas.data_events import DataBatch, Identifier, Provider, Symbol
from packages.schemas.intelligence import (
    ClassificationRequest,
    EvaluationRequest,
    GenerationRequest,
)
from packages.schemas.signals import Signal
from services.controls.engine import preview as preview_controls
from services.decision_engine.store import store_evaluation
from services.macro_intelligence.calendar import calendar_as_of
from services.market_data.coverage import coverage_status
from services.market_data.event_store import (
    ImportConflict,
    check_as_of,
    feed_status,
    import_batch,
    latest_events,
    observation,
)
from services.news_intelligence.assessment_store import classifications_as_of, store_classification
from services.news_intelligence.generation import generate_classification, job_view
from services.news_intelligence.providers.gemini import GeminiAdapter, GeminiError
from services.news_intelligence.queries import news_as_of


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine, sessions = session_factory(settings.database_url)
    app = FastAPI(title="HALAL QUANT", version="0.1.0")
    app.state.engine = engine
    app.state.gemini_adapter_factory = GeminiAdapter

    def authenticate(provided, expected):
        if (
            not expected
            or not provided
            or not hmac.compare_digest(provided.encode(), expected.encode())
        ):
            raise HTTPException(401, "Invalid credentials")

    def dashboard(authorization: Annotated[str | None, Header()] = None):
        authenticate(
            authorization,
            f"Bearer {settings.dashboard_api_key}" if settings.dashboard_api_key else "",
        )

    def webhook(x_webhook_key: Annotated[str | None, Header()] = None):
        authenticate(x_webhook_key, settings.tradingview_webhook_key)

    def data_ingestion(x_data_key: Annotated[str | None, Header()] = None):
        authenticate(x_data_key, settings.data_ingestion_key)

    def analysis(x_analysis_key: Annotated[str | None, Header()] = None):
        authenticate(x_analysis_key, settings.analysis_api_key)

    def persist(operation):
        for attempt in range(2):
            try:
                with sessions.begin() as session:
                    result = operation(session)
                return result
            except ImportConflict as error:
                raise HTTPException(409, str(error)) from error
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            except IntegrityError:
                if attempt:
                    raise HTTPException(409, "Concurrent write conflict") from None
            except SQLAlchemyError:
                raise HTTPException(503, "Data store unavailable") from None

    def cutoff(as_of):
        try:
            return check_as_of(as_of or utcnow(), utcnow())
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/health/live")
    def live():
        return {"status": "ok", "mode": "research", "live_execution": False}

    @app.get("/health/ready")
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(select(SignalRecord.event_id).limit(1))
                connection.execute(select(FeedCoverageRecord.id).limit(1))
                connection.execute(select(AuditRecord.id).limit(1))
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                for table in (
                    DataImport,
                    FeedCoverageRecord,
                    NewsRecord,
                    EconomicRecord,
                    CorporateActionRecord,
                    ClassificationRecord,
                    DecisionRecord,
                    GenerationJob,
                ):
                    connection.execute(select(table.id).limit(1))
                if version != "0005_feed_coverage":
                    raise HTTPException(503, "Database migration required")
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable or migrations missing") from None
        return {"status": "ready"}

    @app.post("/api/v1/webhooks/tradingview", dependencies=[Depends(webhook)])
    def ingest(signal: Signal):
        payload = signal.model_dump(mode="json")
        with sessions() as session:
            existing = session.get(SignalRecord, signal.event_id)
            if existing:
                if existing.payload != payload:
                    raise HTTPException(409, "Event ID reused with different payload")
                return {"event_id": signal.event_id, "duplicate": True, "authorized": False}
            try:
                signal.validate_delivery(utcnow(), timedelta(minutes=15))
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            session.add(
                SignalRecord(event_id=signal.event_id, payload=payload, received_at=utcnow())
            )
            session.add(
                AuditRecord(
                    action="technical_signal_received", subject=signal.event_id, created_at=utcnow()
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.get(SignalRecord, signal.event_id)
                if not existing or existing.payload != payload:
                    raise HTTPException(409, "Conflicting event") from None
                return {"event_id": signal.event_id, "duplicate": True, "authorized": False}
        return {"event_id": signal.event_id, "duplicate": False, "authorized": False}

    @app.get("/api/v1/signals", dependencies=[Depends(dashboard)])
    def signals(limit: Annotated[int, Query(ge=1, le=100)] = 50):
        with sessions() as session:
            records = session.scalars(
                select(SignalRecord)
                .order_by(SignalRecord.received_at.desc(), SignalRecord.event_id)
                .limit(limit)
            )
            return {"items": [record.payload for record in records]}

    @app.post("/api/v1/data/import", dependencies=[Depends(data_ingestion)])
    def ingest_data(batch: DataBatch):
        return persist(lambda session: import_batch(session, batch, utcnow()))

    @app.post("/api/v1/news/classifications/generate", dependencies=[Depends(analysis)])
    def generate_assessment(request: GenerationRequest):
        try:
            return generate_classification(
                sessions,
                request,
                settings,
                utcnow,
                adapter_factory=app.state.gemini_adapter_factory,
            )
        except ImportConflict as error:
            raise HTTPException(409, str(error)) from error
        except GeminiError as error:
            unavailable = error.code in {
                "GEMINI_DISABLED",
                "GEMINI_NOT_CONFIGURED",
                "GEMINI_RATE_LIMITED",
                "GEMINI_UNAVAILABLE",
            }
            raise HTTPException(503 if unavailable else 502, error.code) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except SQLAlchemyError:
            raise HTTPException(
                503, "Generation store unavailable; inspect job before retry"
            ) from None

    @app.get(
        "/api/v1/news/classification-jobs/{classification_id:path}",
        dependencies=[Depends(dashboard)],
    )
    def generation_status(classification_id: Identifier):
        with sessions() as session:
            row = session.get(GenerationJob, classification_id)
            if row is None:
                raise HTTPException(404, "Unknown generation job")
            return job_view(row)

    @app.post("/api/v1/news/classifications", dependencies=[Depends(analysis)])
    def ingest_classification(request: ClassificationRequest):
        return persist(lambda session: store_classification(session, request, utcnow()))

    @app.get("/api/v1/news/classifications", dependencies=[Depends(dashboard)])
    def classifications(
        as_of: AwareDatetime | None = None,
        symbol: Symbol | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        time = cutoff(as_of)
        with sessions() as session:
            return {
                "as_of": time.isoformat(),
                "items": classifications_as_of(session, time, symbol, limit),
            }

    @app.post("/api/v1/decisions/evaluate", dependencies=[Depends(analysis)])
    def evaluate_candidate(request: EvaluationRequest):
        return persist(lambda session: store_evaluation(session, request, utcnow(), settings))

    @app.get("/api/v1/decisions", dependencies=[Depends(dashboard)])
    def decisions(
        as_of: AwareDatetime | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 50
    ):
        time = cutoff(as_of)
        with sessions() as session:
            rows = session.scalars(
                select(DecisionRecord)
                .where(DecisionRecord.created_at <= time)
                .order_by(DecisionRecord.created_at.desc(), DecisionRecord.id)
                .limit(limit)
            )
            return {"as_of": time.isoformat(), "items": [row.response for row in rows]}

    @app.get("/api/v1/decisions/{evaluation_id:path}", dependencies=[Depends(dashboard)])
    def decision(evaluation_id: Identifier):
        with sessions() as session:
            row = session.get(DecisionRecord, evaluation_id)
            if row is None:
                raise HTTPException(404, "Unknown evaluation")
            return row.response

    @app.get("/api/v1/news", dependencies=[Depends(dashboard)])
    def news(
        as_of: AwareDatetime | None = None,
        symbol: Symbol | None = None,
        asset_class: Literal["stock", "etf", "gold"] | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        time = cutoff(as_of)
        with sessions() as session:
            return {
                "as_of": time.isoformat(),
                "items": news_as_of(session, time, symbol, asset_class, limit),
            }

    @app.get("/api/v1/economic-events", dependencies=[Depends(dashboard)])
    def economic_events(
        as_of: AwareDatetime | None = None,
        symbol: Symbol | None = None,
        asset_class: Literal["stock", "etf", "gold"] | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        time = cutoff(as_of)
        with sessions() as session:
            return {
                "as_of": time.isoformat(),
                "items": calendar_as_of(session, time, symbol, asset_class, limit),
            }

    @app.get("/api/v1/corporate-actions", dependencies=[Depends(dashboard)])
    def corporate_actions(
        as_of: AwareDatetime | None = None,
        symbol: Symbol | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        time = cutoff(as_of)
        with sessions() as session:
            rows = latest_events(session, "corporate_actions", time)
            return {
                "as_of": time.isoformat(),
                "items": [
                    observation(row)
                    for row in rows
                    if symbol is None or row.payload["symbol"] == symbol
                ][:limit],
            }

    @app.get("/api/v1/data/status", dependencies=[Depends(dashboard)])
    def data_status(
        provider: Provider,
        kind: Literal["news", "calendar", "corporate_actions"],
        as_of: AwareDatetime | None = None,
        maximum_age_seconds: Annotated[int, Query(ge=1, le=86400)] = 900,
    ):
        time = cutoff(as_of)
        with sessions() as session:
            return feed_status(
                session, provider, kind, time, timedelta(seconds=maximum_age_seconds)
            )

    @app.get("/api/v1/data/coverage", dependencies=[Depends(dashboard)])
    def data_coverage(
        provider: Provider,
        symbol: Symbol,
        asset_class: Literal["stock", "etf", "gold"],
        purpose: Literal["company_news", "earnings", "macro_releases", "corporate_actions"],
        window_start: AwareDatetime,
        window_end: AwareDatetime,
        as_of: AwareDatetime | None = None,
        maximum_age_seconds: Annotated[int, Query(ge=1, le=86400)] = 900,
    ):
        time = cutoff(as_of)
        try:
            with sessions() as session:
                return coverage_status(
                    session,
                    provider,
                    symbol,
                    asset_class,
                    purpose,
                    time,
                    window_start,
                    window_end,
                    timedelta(seconds=maximum_age_seconds),
                )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except SQLAlchemyError:
            raise HTTPException(
                503, "Data store unavailable or coverage migration missing"
            ) from None

    @app.get("/api/v1/audit", dependencies=[Depends(dashboard)])
    def audit(limit: Annotated[int, Query(ge=1, le=100)] = 50):
        with sessions() as session:
            records = session.scalars(
                select(AuditRecord).order_by(AuditRecord.id.desc()).limit(limit)
            )
            return {
                "items": [
                    {
                        "id": r.id,
                        "action": r.action,
                        "subject": r.subject,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in records
                ]
            }

    @app.post("/api/v1/controls/preview", dependencies=[Depends(analysis)])
    def controls_preview(scenario: ControlScenario):
        cutoff(scenario.as_of)
        return preview_controls(scenario)

    return app


app = create_app()
