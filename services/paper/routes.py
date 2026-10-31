"""Workspace-wide synthetic simulator: authenticated reads, operator-only writes."""

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from services.controls.store import lock_controls
from services.market_data.event_store import ImportConflict
from services.paper.engine import mutate, open_account, snapshot
from services.paper.models import PaperAccount, PaperJournal
from services.paper.schemas import (
    CancelRequest,
    Command,
    FillRequest,
    HaltRequest,
    OpenAccount,
    OrderRequest,
    QuoteRequest,
)


def mount_paper(app, sessions, settings, current_user, dashboard):
    current_dependency = Depends(current_user)

    def operator(user=current_dependency):
        if user.role != "operator":
            raise HTTPException(403, "Operator role required for paper operations")
        if not settings.paper_trading_enabled:
            raise HTTPException(503, "Internal synthetic paper simulator is disabled")
        return user.id

    operator_dependency = Depends(operator)

    def write(operation):
        try:
            with sessions.begin() as session:
                return operation(session)
        except ImportConflict as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except SQLAlchemyError:
            raise HTTPException(503, "Paper data store unavailable") from None

    @app.get("/api/v1/paper/accounts", dependencies=[Depends(dashboard)])
    def accounts(limit: int = Query(default=50, ge=1, le=100)):
        with sessions() as session:
            rows = session.scalars(
                select(PaperAccount)
                .order_by(PaperAccount.created_at.desc(), PaperAccount.id)
                .limit(limit)
            ).all()
            return {
                "enabled": settings.paper_trading_enabled,
                "mode": "synthetic",
                "authorized": False,
                "forward_acceptance": "NOT_ESTABLISHED",
                "items": [
                    {"account_id": a.id, "created_at": a.created_at.isoformat()} for a in rows
                ],
            }

    @app.get("/api/v1/paper/accounts/{account_id}", dependencies=[Depends(dashboard)])
    def account(account_id: str):
        with sessions.begin() as session:
            lock_controls(session)
            row = session.get(PaperAccount, account_id)
            if row is None:
                raise HTTPException(404, "Unknown paper account")
            return snapshot(session, row)

    @app.get("/api/v1/paper/accounts/{account_id}/journal", dependencies=[Depends(dashboard)])
    def journal(
        account_id: str,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        with sessions() as session:
            if session.get(PaperAccount, account_id) is None:
                raise HTTPException(404, "Unknown paper account")
            rows = session.scalars(
                select(PaperJournal)
                .where(PaperJournal.account_id == account_id, PaperJournal.sequence > after)
                .order_by(PaperJournal.sequence)
                .limit(limit)
            ).all()
            return {
                "mode": "synthetic",
                "authorized": False,
                "items": [
                    {
                        "sequence": e.sequence,
                        "id": e.id,
                        "created_at": e.created_at.isoformat(),
                        "payload": e.payload,
                        "entry_sha256": e.entry_sha256,
                    }
                    for e in rows
                ],
            }

    @app.post("/api/v1/paper/accounts")
    def create(body: OpenAccount, actor=operator_dependency):
        return write(lambda session: open_account(session, body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/orders")
    def order(account_id: str, body: OrderRequest, actor=operator_dependency):
        return write(lambda session: mutate(session, account_id, "order", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/quotes")
    def quote(account_id: str, body: QuoteRequest, actor=operator_dependency):
        return write(lambda session: mutate(session, account_id, "quote", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/fills")
    def fill(account_id: str, body: FillRequest, actor=operator_dependency):
        return write(lambda session: mutate(session, account_id, "fill", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/cancel")
    def cancel(account_id: str, body: CancelRequest, actor=operator_dependency):
        return write(lambda session: mutate(session, account_id, "cancel", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/tick")
    def tick(account_id: str, body: Command, actor=operator_dependency):
        return write(lambda session: mutate(session, account_id, "tick", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/halt")
    def halt(account_id: str, body: HaltRequest, actor=operator_dependency):
        return write(lambda session: mutate(session, account_id, "halt", body, actor))
