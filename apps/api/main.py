import hmac
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.api.db import AuditRecord, SignalRecord, session_factory, utcnow
from packages.config.settings import Settings, get_settings
from packages.schemas.signals import Signal


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
                if version != "0001_foundation":
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
