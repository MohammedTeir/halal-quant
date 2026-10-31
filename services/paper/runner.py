"""Fenced, restartable internal broker worker; network reads happen outside DB locks."""

import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from apps.api.db import AuditRecord, DecisionRecord, utcnow
from services.controls.store import lock_controls
from services.market_data.event_store import aware, digest
from services.paper import engine
from services.paper.forward import (
    ACTIVE,
    approved_run,
    corporate_events,
    cycle_seal,
    decision_order,
    owned_before_action,
    report,
)
from services.paper.models import PaperAccount, PaperCycle, PaperRun
from services.paper.provider import MarketBundle
from services.paper.schemas import (
    CancelRequest,
    Command,
    DecisionOrder,
    FillRequest,
    OpenAccount,
    OrderRequest,
)


class LeaseLost(ValueError):
    pass


class CriticalCycle(ValueError):
    pass


def claim(sessions, run_id, owner, now=None):
    with sessions.begin() as db:
        lock_controls(db)
        now = now or utcnow()
        run = db.get(PaperRun, run_id)
        if not run:
            raise ValueError("Unknown forward run")
        account = db.get(PaperAccount, run.account_id)
        approved_run(db, account, now, current_entry_review=False)
        state = run.state
        if state.get("last_seen") and now < aware(datetime.fromisoformat(state["last_seen"])):
            raise ValueError("Paper worker clock moved backwards")
        live = state.get("lease_until") and now < aware(
            datetime.fromisoformat(state["lease_until"])
        )
        if live and state.get("owner") != owner:
            raise LeaseLost("Another paper worker holds the run lease")
        generation = state["generation"] + (0 if live and state.get("owner") == owner else 1)
        run.state = state | {
            "owner": owner,
            "lease_until": (
                now + timedelta(seconds=max(120, run.protocol["cadence_seconds"] * 3))
            ).isoformat(),
            "generation": generation,
            "started_at": state.get("started_at") or now.isoformat(),
            "status": "RUNNING",
        }
        return {
            "generation": generation,
            "worker_id": owner,
            "account_id": account.id,
            "config": account.config,
            "protocol": run.protocol,
            "cycle_id": secrets.token_hex(32),
            "started_at": now,
        }


def fence(db, run_id, owner, generation, now):
    run = db.get(PaperRun, run_id)
    if (
        not run
        or run.state.get("owner") != owner
        or run.state["generation"] != generation
        or not run.state.get("lease_until")
        or now >= aware(datetime.fromisoformat(run.state["lease_until"]))
    ):
        raise LeaseLost("Paper worker lease expired or changed")
    if run.state["status"] not in ACTIVE:
        raise LeaseLost("Forward run is no longer active")
    return run


def release(sessions, run_id, owner):
    with sessions.begin() as db:
        lock_controls(db)
        run = db.get(PaperRun, run_id)
        if run and run.state.get("owner") == owner:
            run.state = run.state | {
                "owner": None,
                "lease_until": None,
                "data_available": False,
                "status": "PAUSED" if run.state["status"] == "RUNNING" else run.state["status"],
            }


def append_cycle(db, run, claim_data, now, payload):
    payload = payload | {"worker_id": claim_data["worker_id"]}
    prior = db.scalar(
        select(PaperCycle)
        .where(PaperCycle.run_id == run.id)
        .order_by(PaperCycle.sequence.desc())
        .limit(1)
    )
    previous = prior.entry_sha256 if prior else engine.ZERO_HASH
    row = PaperCycle(
        id=claim_data["cycle_id"],
        run_id=run.id,
        started_at=claim_data["started_at"],
        completed_at=now,
        payload=payload,
        previous_sha256=previous,
        entry_sha256=cycle_seal(
            run.id, claim_data["cycle_id"], claim_data["started_at"], now, previous, payload
        ),
    )
    db.add(row)
    critical = run.state.get("critical_violations", [])
    if payload["status"] == "CRITICAL":
        critical = sorted({*critical, payload["error"]})
    run.state = run.state | {
        "last_seen": now.isoformat(),
        "status": "FAILED"
        if critical
        else "PAUSED"
        if payload["status"] == "PAUSED"
        else "RUNNING",
        "critical_violations": critical,
        "last_status": payload["status"],
        "last_error": payload.get("error"),
        "data_available": payload["status"] == "OK",
    }
    db.add(
        AuditRecord(
            action="paper.cycle_" + payload["status"].lower(), subject=run.id, created_at=now
        )
    )
    db.flush()
    return {
        "run_id": run.id,
        "status": payload["status"],
        "generation": run.state["generation"],
        "error": payload.get("error"),
        "results": payload.get("results", []),
    }


def problem(sessions, run_id, owner, claim_data, code, *, critical=False, now=None):
    with sessions.begin() as db:
        lock_controls(db)
        now = now or utcnow()
        prior = db.scalar(select(PaperCycle).where(PaperCycle.id == claim_data["cycle_id"]))
        if prior:
            return {"status": prior.payload["status"], "duplicate": True}
        run = fence(db, run_id, owner, claim_data["generation"], now)
        return append_cycle(
            db,
            run,
            claim_data,
            now,
            {
                "status": "CRITICAL" if critical else "PAUSED",
                "error": code,
                "generation": claim_data["generation"],
                "results": [],
            },
        )


def process(sessions, run_id, owner, claim_data, bundle, now=None):
    # Validate the source receipt before touching ledger or consumption counters.
    injected_now = now is not None
    clock = (lambda: now) if injected_now else utcnow
    bundle = MarketBundle.model_validate(bundle)
    with sessions.begin() as db:
        lock_controls(db)
        now = now or utcnow()
        prior = db.scalar(select(PaperCycle).where(PaperCycle.id == claim_data["cycle_id"]))
        if prior:
            return {"status": prior.payload["status"], "duplicate": True}
        run = fence(db, run_id, owner, claim_data["generation"], now)
        account = db.get(PaperAccount, run.account_id)
        approved_run(db, account, now, current_entry_review=False)
        if (
            now < claim_data["started_at"]
            or not now - timedelta(seconds=15) <= bundle.received_at <= now
        ):
            raise ValueError("Provider receipt is stale or in the future")
        check = engine.reconcile(db, account)
        if check["status"] != "MATCH":
            return append_cycle(
                db,
                run,
                claim_data,
                now,
                {
                    "status": "CRITICAL",
                    "error": "RECONCILIATION_MISMATCH",
                    "results": [],
                    "generation": claim_data["generation"],
                },
            )
        prior_cycle = db.scalar(
            select(PaperCycle)
            .where(PaperCycle.run_id == run.id)
            .order_by(PaperCycle.sequence.desc())
            .limit(1)
        )
        pre_owned = len(account.state["positions"])
        pre_open = sum(
            1
            for order in engine.orders(db, account.id)
            if order.state["status"] in engine.OPEN
            and aware(datetime.fromisoformat(order.state["expires_at"])) > now
        )
        recovery = {
            "verified": bool(
                prior_cycle
                and prior_cycle.payload.get("worker_id") != owner
                and prior_cycle.payload.get("ledger_after") == check["last_entry_sha256"]
                and (pre_owned or pre_open)
            ),
            "owned_positions": pre_owned,
            "open_orders": pre_open,
        }
        db.info["paper_cycle_verified"] = account.id
        config = OpenAccount.model_validate(account.config)
        events = corporate_events(db, account, now)
        overdue = [
            e
            for e in events
            if aware(datetime.fromisoformat(e.payload["effective_at"])) <= now
            and owned_before_action(db, account, e)
        ]
        if overdue:
            return append_cycle(
                db,
                run,
                claim_data,
                now,
                {
                    "status": "CRITICAL",
                    "error": "CORPORATE_ACTION_MISSED_EXIT",
                    "results": [],
                    "generation": claim_data["generation"],
                    "action_ids": [e.id for e in overdue],
                },
            )
        results = []

        def execute(kind, body):
            result = engine.mutate(
                db,
                account.id,
                kind,
                body,
                "paper-worker",
                clock() if injected_now else None,
                authority=engine.WORKER_AUTHORITY,
                already_locked=True,
            )
            if result.get("reason") == "RECONCILIATION_MISMATCH":
                raise ValueError("Ledger reconciliation failed")
            results.append(result)
            return result

        def complete(payload):
            final = engine.reconcile(db, account)
            if final["status"] != "MATCH":
                raise CriticalCycle("POST_CYCLE_RECONCILIATION_MISMATCH")
            finished_at = clock()
            fence(db, run_id, owner, claim_data["generation"], finished_at)
            payload = payload | {
                "ledger_before": check["last_entry_sha256"],
                "ledger_after": final["last_entry_sha256"],
                "recovery": recovery,
            }
            return append_cycle(db, run, claim_data, finished_at, payload)

        prefix = "worker:" + claim_data["cycle_id"][:24]
        execute("tick", Command(command_id=prefix + ":tick"))
        session = next((s for s in bundle.sessions if s.opens <= now < s.closes), None)
        if not bundle.market_open or session is None:
            if bundle.market_open:
                raise ValueError("Clock/session changed during snapshot")
            return complete(
                {
                    "status": "CLOSED",
                    "market_open": False,
                    "receipt_sha256": bundle.receipt_sha256,
                    "generation": claim_data["generation"],
                    "results": results,
                }
            )
        mapping = {
            config.provider_symbols.get(symbol, symbol): symbol for symbol in config.universe
        }
        if set(bundle.quotes) | set(bundle.missing_symbols) != set(mapping):
            raise ValueError("Complete configured quote snapshot required")
        missing = {mapping[ticker] for ticker in bundle.missing_symbols}
        run.state = run.state | {"data_available": not missing}
        for ticker, q in bundle.quotes.items():
            symbol = mapping[ticker]
            body = q.model_copy(update={"symbol": symbol})
            old = engine.current_quote(db, account.id, symbol)
            if (
                old
                and aware(datetime.fromisoformat(old.payload["observed_at"])) >= body.observed_at
            ):
                # An unchanged snapshot never replenishes already consumed liquidity.
                continue
            execute("quote", body)
        # Cancel new risk first when the account is halted or an exclusion starts.
        upcoming = {
            e.payload["symbol"]
            for e in events
            if now - timedelta(days=1)
            <= aware(datetime.fromisoformat(e.payload["effective_at"]))
            <= now + timedelta(days=3)
        }
        for order in engine.orders(db, account.id):
            if (
                order.state["status"] in engine.OPEN
                and order.request["side"] == "BUY"
                and (
                    order.request["symbol"] in upcoming or account.state["halted"] or bool(missing)
                )
            ):
                execute(
                    "cancel",
                    CancelRequest(command_id=prefix + ":cancel:" + order.id, order_id=order.id),
                )
        # Standing owned exits use the position stop; they do not require positive
        # news, entry approval, or a new AI decision. They remain ordinary sells.
        for symbol, position in list(account.state["positions"].items()):
            if symbol in missing:
                continue
            q = engine.current_quote(db, account.id, symbol)
            if not engine.fresh(q, now, config.policy.quote_max_age_seconds):
                continue
            if (
                Decimal(q.payload["bid"]) > Decimal(position["stop"])
                and symbol not in upcoming
                and not account.state.get("liquidation_requested")
            ):
                continue
            pending_protection = [
                o
                for o in engine.orders(db, account.id)
                if o.state["status"] in engine.OPEN
                and o.request["symbol"] == symbol
                and ":protect:" in o.request["command_id"]
                and o.request["side"] == "SELL"
            ]
            if pending_protection:
                continue
            # Cancel existing sell remainders before a protective replacement so
            # reservations never overstate owned/sellable shares.
            for order in engine.orders(db, account.id):
                if order.state["status"] in engine.OPEN and order.request["symbol"] == symbol:
                    execute(
                        "cancel",
                        CancelRequest(
                            command_id=prefix + ":replace:" + order.id, order_id=order.id
                        ),
                    )
            execute(
                "order",
                OrderRequest(
                    command_id=prefix + ":protect:" + digest(symbol)[:16],
                    symbol=symbol,
                    side="SELL",
                    quantity=position["quantity"],
                    expires_in_seconds=86400,
                ),
            )
        # Match existing orders first. A new order cannot use an observation from
        # before/equal its submission; protection waits for the next fresh tick.
        for order in engine.orders(db, account.id):
            if (
                order.state["status"] not in engine.OPEN
                or order.request["symbol"] in missing
                or (missing and order.request["side"] == "BUY")
            ):
                continue
            q = engine.current_quote(db, account.id, order.request["symbol"])
            if (
                q
                and aware(datetime.fromisoformat(q.payload["observed_at"]))
                > aware(order.created_at)
                and aware(q.created_at) > aware(order.created_at)
            ):
                execute(
                    "fill",
                    FillRequest(
                        command_id=prefix + ":fill:" + order.id, order_id=order.id, quote_id=q.id
                    ),
                )
        # Consume only stored, fresh decisions, one deterministic command per ID.
        decisions = db.scalars(
            select(DecisionRecord)
            .where(
                DecisionRecord.created_at <= now,
                DecisionRecord.created_at
                >= now - timedelta(seconds=run.protocol["decision_max_age_seconds"]),
            )
            .order_by(DecisionRecord.created_at.desc(), DecisionRecord.id)
            .limit(50)
        ).all()
        for decision in decisions:
            signal = decision.response.get("snapshot", {}).get("signal", {})
            symbol = signal.get("symbol")
            if symbol not in config.universe or missing:
                continue
            command_id = engine.key(account.id, "signal:" + digest({"id": decision.signal_id}))
            from services.paper.models import PaperJournal

            if db.scalar(select(PaperJournal).where(PaperJournal.id == command_id)):
                continue
            q = engine.current_quote(db, account.id, symbol)
            if not q:
                continue
            quantity = run.protocol["quantity_per_decision"]
            if signal.get("action") == "EXIT_CANDIDATE":
                reserved = sum(
                    o.state["reserved_shares"]
                    for o in engine.orders(db, account.id)
                    if o.state["status"] in engine.OPEN and o.request["symbol"] == symbol
                )
                quantity = max(
                    0, account.state["positions"].get(symbol, {}).get("quantity", 0) - reserved
                )
                if not quantity:
                    continue
            try:
                result = decision_order(
                    db,
                    account.id,
                    DecisionOrder(
                        decision_id=decision.id,
                        quantity=quantity,
                        stop_price=Decimal(q.payload["ask"])
                        * (1 - Decimal(run.protocol["stop_fraction"])),
                    ),
                    "paper-worker",
                    clock() if injected_now else None,
                    already_locked=True,
                )
                results.append(result)
            except ValueError:
                # A decision lacking current evidence is not executable. Record a
                # guarded observation, never invent an approval or change the source.
                results.append({"status": "DECISION_BLOCKED", "decision_id": decision.id})
        payload = {
            "status": "PAUSED" if missing else "OK",
            "missing_symbols": sorted(missing),
            "market_open": True,
            "session": session.model_dump(mode="json"),
            "receipt_sha256": bundle.receipt_sha256,
            "generation": claim_data["generation"],
            "results": results,
        }
        if missing:
            payload["error"] = "PARTIAL_MARKET_DATA"
        return complete(payload)


def finalize(session, run_id, actor, now=None):
    lock_controls(session)
    now = now or utcnow()
    run = session.get(PaperRun, run_id)
    if not run:
        raise ValueError("Unknown forward run")
    if run.state["status"] == "COMPLETED":
        return run.state["final_report"]
    result = report(session, run, now)
    if result["status"] != "ACCEPTABLE":
        return result
    result = result | {"status": "PASSED", "state": "COMPLETED", "completed_at": now.isoformat()}
    run.state = run.state | {
        "status": "COMPLETED",
        "owner": None,
        "lease_until": None,
        "final_report": result,
        "final_report_sha256": digest(result),
    }
    session.add(AuditRecord(action="paper.forward_completed", subject=run.id, created_at=now))
    return result
