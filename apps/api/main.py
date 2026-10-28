import hmac
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.api.db import (
    AuditRecord,
    CorporateActionRecord,
    DataImport,
    EconomicRecord,
    NewsRecord,
    SignalRecord,
    session_factory,
    utcnow,
)
from packages.config.settings import Settings, get_settings
from packages.schemas.data_events import DataBatch, Provider, Symbol
from packages.schemas.signals import Signal
from services.macro_intelligence.calendar import calendar_as_of
from services.market_data.event_store import (
    ImportConflict,
    check_as_of,
    feed_status,
    import_batch,
    latest_events,
    observation,
)
from services.news_intelligence.queries import news_as_of


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine, sessions = session_factory(settings.database_url)
    app = FastAPI(title="HALAL QUANT", version="0.1.0")
    app.state.engine = engine

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
                connection.execute(select(AuditRecord.id).limit(1))
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                for table in (DataImport, NewsRecord, EconomicRecord, CorporateActionRecord):
                    connection.execute(select(table.id).limit(1))
                if version != "0002_data_events":
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
        # Retry only a diagnosed unique-key race; rollback leaves no partial batch/audit.
        for attempt in range(2):
            try:
                with sessions.begin() as session:
                    result = import_batch(session, batch, utcnow())
                return result
            except ImportConflict as error:
                raise HTTPException(409, str(error)) from error
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            except IntegrityError:
                if attempt:
                    raise HTTPException(409, "Concurrent data import conflict") from None
            except SQLAlchemyError:
                raise HTTPException(503, "Data store unavailable") from None

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

    return app


app = create_app()
