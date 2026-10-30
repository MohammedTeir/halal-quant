"""Durable at-most-one refresh claim; no database transaction spans broker HTTP."""

from apps.api.db import AuditRecord, BrokerCapture, utcnow
from services.controls.broker import BrokerError
from services.controls.store import capture_view, get_capture, lock_controls
from services.market_data.event_store import ImportConflict, digest


def refresh(sessions, refresh_id, kind, symbol, adapter_factory):
    checksum = digest({"kind": kind, "symbol": symbol})
    with sessions.begin() as session:
        lock_controls(session)
        record = get_capture(session, refresh_id)
        if record:
            if record.request_sha256 != checksum:
                raise ImportConflict("Broker refresh ID conflict")
            # Failed/RUNNING requests are deliberately not automatically resumed.
            return capture_view(record) | {"duplicate": True}
        record = BrokerCapture(
            id=refresh_id,
            request_sha256=checksum,
            kind=kind,
            scope=symbol,
            status="RUNNING",
            created_at=utcnow(),
        )
        session.add(record)
        session.add(
            AuditRecord(action="broker_refresh_started", subject=refresh_id, created_at=utcnow())
        )
    try:
        adapter = adapter_factory()
        payload = adapter.account() if kind == "account" else adapter.quote(symbol)
        code = None
    except BrokerError as error:
        payload = None
        code = str(error)
    # Unknown process/adapter failures leave RUNNING, preventing blind retries.
    with sessions.begin() as session:
        lock_controls(session)
        record = get_capture(session, refresh_id)
        record.status = "SUCCEEDED" if payload is not None else "FAILED"
        record.completed_at = utcnow()
        record.error_code = code
        record.payload = payload
        if payload is not None:
            record.scope = payload["account_id"] if kind == "account" else payload["symbol"]
        session.add(
            AuditRecord(
                action="broker_refresh_" + record.status.lower(),
                subject=refresh_id,
                created_at=utcnow(),
            )
        )
        session.flush()
        return capture_view(record) | {"duplicate": False}
