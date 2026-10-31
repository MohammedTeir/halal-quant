"""Workspace-wide internal simulator: authenticated reads, role-gated writes."""

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from services.controls.store import lock_controls
from services.market_data.event_store import ImportConflict
from services.paper import forward
from services.paper.engine import mutate, open_account, snapshot
from services.paper.models import PaperAccount, PaperJournal, PaperRun
from services.paper.runner import finalize
from services.paper.schemas import (
    CancelRequest,
    Command,
    DecisionOrder,
    ExitRequest,
    FillRequest,
    ForwardProtocol,
    HaltRequest,
    OpenAccount,
    OrderRequest,
    QuoteRequest,
    ReviewRun,
)


def mount_paper(app, sessions, settings, current_user, dashboard):
    current_dependency = Depends(current_user)

    def operator_identity(user=current_dependency):
        if user.role != "operator":
            raise HTTPException(403, "Operator role required for paper operations")
        return user.id

    cleanup_dependency = Depends(operator_identity)

    def operator(user=current_dependency):
        if user.role != "operator":
            raise HTTPException(403, "Operator role required for paper operations")
        if not settings.paper_trading_enabled:
            raise HTTPException(503, "Internal paper simulator is disabled")
        return user.id

    operator_dependency = Depends(operator)

    def forward_operator(user=current_dependency):
        if user.role != "operator":
            raise HTTPException(403, "Operator role required")
        if not settings.paper_trading_enabled or not settings.paper_forward_enabled:
            raise HTTPException(503, "Paper forward mode is disabled")
        return user.id

    def reviewer(user=current_dependency):
        if user.role != "reviewer":
            raise HTTPException(403, "Reviewer role required")
        if not settings.paper_forward_enabled:
            raise HTTPException(503, "Paper forward mode is disabled")
        return user.id

    forward_dependency = Depends(forward_operator)
    reviewer_dependency = Depends(reviewer)

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
                "mode": "internal_paper",
                "forward_enabled": settings.paper_forward_enabled,
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
            account = session.get(PaperAccount, account_id)
            if account is None:
                raise HTTPException(404, "Unknown paper account")
            rows = session.scalars(
                select(PaperJournal)
                .where(PaperJournal.account_id == account_id, PaperJournal.sequence > after)
                .order_by(PaperJournal.sequence)
                .limit(limit)
            ).all()
            return {
                "mode": account.config.get("mode", "synthetic"),
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
        if body.mode == "forward" and not settings.paper_forward_enabled:
            raise HTTPException(503, "Paper forward mode is disabled")
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
    def cancel(account_id: str, body: CancelRequest, actor=cleanup_dependency):
        return write(lambda session: mutate(session, account_id, "cancel", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/tick")
    def tick(account_id: str, body: Command, actor=cleanup_dependency):
        return write(lambda session: mutate(session, account_id, "tick", body, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/halt")
    def halt(account_id: str, body: HaltRequest, actor=cleanup_dependency):
        def operation(session):
            lock_controls(session)
            account = session.get(PaperAccount, account_id)
            if not body.engaged and (
                not settings.paper_trading_enabled
                or (
                    account
                    and account.config.get("mode") == "forward"
                    and not settings.paper_forward_enabled
                )
            ):
                raise HTTPException(503, "Cannot resume disabled paper operations")
            return mutate(session, account_id, "halt", body, actor, already_locked=True)

        return write(operation)

    @app.post("/api/v1/paper/accounts/{account_id}/decision-orders")
    def bridge(account_id: str, body: DecisionOrder, actor=forward_dependency):
        return write(lambda session: forward.decision_order(session, account_id, body, actor))

    @app.post("/api/v1/paper/runs")
    def propose(body: ForwardProtocol, actor=forward_dependency):
        return write(lambda session: forward.propose(session, body, actor))

    @app.post("/api/v1/paper/runs/{run_id}/review")
    def review(run_id: str, body: ReviewRun, actor=reviewer_dependency):
        return write(lambda session: forward.review(session, run_id, body, actor))

    @app.get("/api/v1/paper/runs", dependencies=[Depends(dashboard)])
    def runs(limit: int = Query(default=50, ge=1, le=100)):
        with sessions() as session:
            rows = session.scalars(
                select(PaperRun).order_by(PaperRun.created_at.desc()).limit(limit)
            ).all()
            return {
                "items": [
                    {
                        "run_id": r.id,
                        "account_id": r.account_id,
                        "account_config": session.get(PaperAccount, r.account_id).config
                        if session.get(PaperAccount, r.account_id)
                        else None,
                        "protocol": r.protocol,
                        "state": r.state,
                        "protocol_sha256": forward.protocol_hash(r),
                    }
                    for r in rows
                ]
            }

    @app.get("/api/v1/paper/runs/{run_id}", dependencies=[Depends(dashboard)])
    def run_status(run_id: str):
        with sessions.begin() as session:
            lock_controls(session)
            run = session.get(PaperRun, run_id)
            if not run:
                raise HTTPException(404, "Unknown forward run")
            return forward.report(session, run)

    @app.post("/api/v1/paper/runs/{run_id}/finalize")
    def finish(run_id: str, actor=forward_dependency):
        return write(lambda session: finalize(session, run_id, actor))

    @app.post("/api/v1/paper/accounts/{account_id}/liquidate")
    def liquidate(account_id: str, body: ExitRequest, actor=cleanup_dependency):
        return write(lambda session: mutate(session, account_id, "liquidate", body, actor))
