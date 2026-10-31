from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from services.market_data.event_store import ImportConflict
from services.paper import engine
from services.paper.models import PaperAccount, PaperJournal, PaperOrder, PaperQuote
from services.paper.schemas import (
    CancelRequest,
    Command,
    FillRequest,
    HaltRequest,
    OpenAccount,
    OrderRequest,
    QuoteRequest,
)


@pytest.fixture
def sim(client):
    sessions = sessionmaker(client.app.state.engine, expire_on_commit=False)
    now = datetime(2026, 10, 31, 12, tzinfo=UTC)
    with sessions.begin() as db:
        engine.open_account(
            db,
            OpenAccount(account_id="paper-test", universe={"SYNTH": "technology"}),
            "operator",
            now,
        )
    return sessions, now


def run(sim, kind, body, seconds=0, account="paper-test"):
    sessions, now = sim
    with sessions.begin() as db:
        return engine.mutate(db, account, kind, body, "operator", now + timedelta(seconds=seconds))


def quote(sim, name="q1", seconds=0, bid="99", ask="100", size=100):
    return run(
        sim,
        "quote",
        QuoteRequest(
            command_id=name,
            symbol="SYNTH",
            observed_at=sim[1] + timedelta(seconds=seconds),
            bid=bid,
            ask=ask,
            bid_size=size,
            ask_size=size,
        ),
        seconds,
    )["quote_id"]


def buy(sim, name="buy", quantity=10, **kwargs):
    return run(
        sim,
        "order",
        OrderRequest(
            command_id=name,
            symbol="SYNTH",
            side="BUY",
            quantity=quantity,
            stop_price="95",
            **kwargs,
        ),
    )


def state(sim):
    with sim[0]() as db:
        return engine.snapshot(db, db.get(PaperAccount, "paper-test"))


def fill(sim, order, q, name="fill", seconds=1):
    return run(sim, "fill", FillRequest(command_id=name, order_id=order, quote_id=q), seconds)


def test_cash_ownership_partial_fills_settlement_and_restart(sim):
    quote(sim)
    submitted = buy(sim, quantity=10)
    assert "order_id" in submitted, submitted
    order = submitted["order_id"]
    assert state(sim)["available_cash"] == "99000"
    q = quote(sim, "q2", 1, size=4)
    result = fill(sim, order, q)
    assert result["status"] == "PARTIALLY_FILLED"
    assert result["fill"]["quantity"] == 4
    assert fill(sim, order, q, "empty", 2)["reason"] == "QUOTE_LIQUIDITY_EXHAUSTED"
    q = quote(sim, "q3", 3, size=100)
    assert fill(sim, order, q, "complete", 3)["status"] == "FILLED"
    assert state(sim)["state"]["positions"]["SYNTH"]["quantity"] == 10
    assert Decimal(state(sim)["state"]["cash"]) == 99000
    sell = run(
        sim, "order", OrderRequest(command_id="sell", symbol="SYNTH", side="SELL", quantity=10), 4
    )["order_id"]
    q = quote(sim, "q4", 5, bid="110", ask="111")
    assert fill(sim, sell, q, "exit", 5)["status"] == "FILLED"
    snap = state(sim)
    assert snap["state"]["positions"] == {}
    assert Decimal(snap["state"]["cash"]) == 99000
    assert Decimal(snap["equity"]) == 100100
    assert Decimal(snap["state"]["realized"]) == 100
    assert run(sim, "tick", Command(command_id="early"), 6)["settlements"] == 0
    assert run(sim, "tick", Command(command_id="settle"), 172806)["settlements"] == 1
    assert Decimal(state(sim)["state"]["cash"]) == 100100
    # New SQLAlchemy connection/session simulates a worker restart; no memory balances.
    sim[0].kw["bind"].dispose()
    assert state(sim)["reconciliation"]["status"] == "MATCH"


def test_idempotency_and_conflicts_do_not_duplicate_orders_or_fills(sim):
    quote(sim)
    first = buy(sim)
    assert buy(sim)["duplicate"]
    with pytest.raises(ImportConflict):
        buy(sim, quantity=11)
    q = quote(sim, "q2", 1)
    first_fill = fill(sim, first["order_id"], q)
    assert fill(sim, first["order_id"], q)["duplicate"]
    assert first_fill["fill"]["quantity"] == 10
    with sim[0]() as db:
        assert len(db.scalars(select(PaperOrder)).all()) == 1
    assert state(sim)["state"]["positions"]["SYNTH"]["quantity"] == 10


def test_reservations_prevent_overspending_and_short_sales(sim):
    quote(sim)
    # Each 100-share order reaches the default 10% position cap.
    assert buy(sim, quantity=100)["status"] == "ACCEPTED"
    assert buy(sim, "second", quantity=1)["status"] == "REJECTED"
    short = run(
        sim, "order", OrderRequest(command_id="short", symbol="SYNTH", side="SELL", quantity=1)
    )
    assert short["status"] == "REJECTED" and "INSUFFICIENT_OWNED_SHARES" in short["reasons"]
    assert state(sim)["reconciliation"]["status"] == "MATCH"


def test_cancel_and_expiry_release_holds(sim):
    quote(sim)
    first = buy(sim)["order_id"]
    run(sim, "cancel", CancelRequest(command_id="cancel", order_id=first))
    assert Decimal(state(sim)["available_cash"]) == 100000
    buy(sim, "expires", expires_in_seconds=1)
    assert run(sim, "tick", Command(command_id="expire"), 2)["expired_orders"] == 1
    assert Decimal(state(sim)["available_cash"]) == 100000


def test_quote_before_order_cannot_fill_and_stale_or_future_quote_rejected(sim):
    q = quote(sim)
    result = run(
        sim,
        "order",
        OrderRequest(command_id="later", symbol="SYNTH", side="BUY", quantity=1, stop_price="95"),
        1,
    )
    with pytest.raises(ValueError, match="after order"):
        fill(sim, result["order_id"], q, seconds=2)
    for observed in (-100, 100):
        with pytest.raises(ValueError, match="stale or in the future"):
            run(
                sim,
                "quote",
                QuoteRequest(
                    command_id="bad",
                    symbol="SYNTH",
                    observed_at=sim[1] + timedelta(seconds=observed),
                    bid="99",
                    ask="100",
                    bid_size=100,
                    ask_size=100,
                ),
                seconds=2,
            )


def test_limit_does_not_fill_above_its_bound(sim):
    quote(sim)
    order = buy(sim, order_type="LIMIT", limit_price="98")["order_id"]
    q = quote(sim, "q2", 1)
    assert fill(sim, order, q)["reason"] == "PRICE_OUTSIDE_BOUND"
    q = quote(sim, "q3", 2, bid="96", ask="97")
    assert fill(sim, order, q, "limit-hit", 2)["fill"]["price"] == "97"


def test_halt_cancels_buys_and_prevents_new_entry(sim):
    quote(sim)
    buy(sim)
    run(sim, "halt", HaltRequest(command_id="halt", engaged=True, reason="Acceptance risk halt"))
    assert state(sim)["orders"][0]["state"]["status"] == "CANCELLED"
    assert "KILL_SWITCH_ACTIVE" in buy(sim, "blocked")["reasons"]
    assert Decimal(state(sim)["available_cash"]) == 100000


@pytest.mark.parametrize("table", ["account", "order", "quote", "journal"])
def test_reconciliation_drift_blocks_mutations_without_repair(sim, table):
    quote(sim)
    buy(sim)
    with sim[0].begin() as db:
        if table == "account":
            row = db.get(PaperAccount, "paper-test")
            row.state = row.state | {"cash": "999999"}
        elif table == "order":
            row = db.scalar(select(PaperOrder))
            row.state = row.state | {"reserved_cash": "0"}
        elif table == "quote":
            row = db.scalar(select(PaperQuote))
            row.payload = row.payload | {"ask": "1"}
        else:
            row = db.scalar(select(PaperJournal).order_by(PaperJournal.sequence))
            row.entry_sha256 = "f" * 64
    assert state(sim)["reconciliation"]["status"] == "MISMATCH"
    assert run(sim, "tick", Command(command_id="blocked"))["reason"] == "RECONCILIATION_MISMATCH"


def test_fees_slippage_cash_and_cost_basis_are_exact(client):
    from packages.schemas.controls import ControlPolicy

    sessions = sessionmaker(client.app.state.engine, expire_on_commit=False)
    now = datetime(2026, 10, 31, 12, tzinfo=UTC)
    with sessions.begin() as db:
        engine.open_account(
            db,
            OpenAccount(
                account_id="paper-test",
                universe={"SYNTH": "technology"},
                policy=ControlPolicy(fee_per_order="1", fee_per_share="0.10", slippage_bps="10"),
            ),
            "operator",
            now,
        )
    sim = sessions, now
    quote(sim)
    order = buy(sim)["order_id"]
    q = quote(sim, "q2", 1, size=4)
    first = fill(sim, order, q)
    assert Decimal(first["fill"]["price"]) == Decimal("100.100")
    assert Decimal(first["fill"]["fee"]) == Decimal("1.40")
    q = quote(sim, "q3", 2)
    second = fill(sim, order, q, "second", 2)
    assert Decimal(second["fill"]["fee"]) == Decimal("0.60")
    assert Decimal(state(sim)["state"]["cash"]) == Decimal("98997.000")
    assert Decimal(state(sim)["state"]["positions"]["SYNTH"]["cost"]) == Decimal("1003.000")
    assert state(sim)["reconciliation"]["status"] == "MATCH"


def test_external_controls_kill_switch_is_rechecked_at_fill(sim):
    from apps.api.db import ControlRevision

    quote(sim)
    order = buy(sim)["order_id"]
    q = quote(sim, "q2", 1)
    with sim[0].begin() as db:
        db.add(
            ControlRevision(
                record_id="risk-kill",
                kind="kill",
                scope="paper-test",
                request_sha256="0" * 64,
                actor="risk-operator",
                received_at=sim[1],
                effective_at=sim[1],
                expires_at=None,
                payload={"engaged": True},
            )
        )
    result = fill(sim, order, q)
    assert result["status"] == "CANCELLED"
    assert "KILL_SWITCH_ACTIVE" in result["reasons"]
    assert state(sim)["state"]["positions"] == {}
    assert Decimal(state(sim)["available_cash"]) == 100000


def test_cannot_reserve_same_owned_shares_for_two_exits(sim):
    quote(sim)
    order = buy(sim)["order_id"]
    q = quote(sim, "q2", 1)
    fill(sim, order, q)
    first = run(
        sim, "order", OrderRequest(command_id="sell1", symbol="SYNTH", side="SELL", quantity=10), 2
    )
    second = run(
        sim, "order", OrderRequest(command_id="sell2", symbol="SYNTH", side="SELL", quantity=1), 2
    )
    assert first["status"] == "ACCEPTED"
    assert second["status"] == "REJECTED"
    assert "INSUFFICIENT_OWNED_SHARES" in second["reasons"]


def test_cash_cannot_be_reused_before_settlement(sim):
    quote(sim)
    bought = buy(sim)["order_id"]
    q = quote(sim, "q2", 1)
    fill(sim, bought, q)
    sell = run(
        sim, "order", OrderRequest(command_id="sell", symbol="SYNTH", side="SELL", quantity=10), 2
    )["order_id"]
    q = quote(sim, "q3", 3)
    fill(sim, sell, q, "sold", 3)
    assert Decimal(state(sim)["available_cash"]) == 99000
    assert sum(Decimal(v["amount"]) for v in state(sim)["state"]["unsettled"].values()) == 990


def test_cross_account_fill_and_reserved_command_ids_rejected(sim):
    with sim[0].begin() as db:
        engine.open_account(
            db,
            OpenAccount(account_id="other", universe={"SYNTH": "technology"}),
            "operator",
            sim[1],
        )
    quote(sim)
    order = buy(sim)["order_id"]
    with pytest.raises(ValueError, match="Unknown order"):
        run(
            sim,
            "cancel",
            CancelRequest(command_id="wrong-account", order_id=order),
            account="other",
        )
    with pytest.raises(ImportConflict, match="Reserved"):
        run(sim, "tick", Command(command_id="__open__"))


def test_fill_while_halted_cannot_open_position_but_owned_exit_is_allowed(sim):
    quote(sim)
    order = buy(sim)["order_id"]
    q = quote(sim, "q2", 1)
    fill(sim, order, q)
    run(sim, "halt", HaltRequest(command_id="halt", engaged=True, reason="Manual test halt"), 2)
    sell = run(
        sim, "order", OrderRequest(command_id="exit", symbol="SYNTH", side="SELL", quantity=10), 3
    )
    assert sell["status"] == "ACCEPTED"
    q = quote(sim, "q3", 4)
    assert fill(sim, sell["order_id"], q, "exit-filled", 4)["status"] == "FILLED"


def test_orders_cannot_widen_existing_position_stop(sim):
    quote(sim)
    buy(sim)
    result = run(
        sim,
        "order",
        OrderRequest(
            command_id="wider-stop", symbol="SYNTH", side="BUY", quantity=1, stop_price="90"
        ),
    )
    assert result["status"] == "REJECTED"
    assert "POSITION_STOP_MISMATCH" in result["reasons"]


def test_parallel_cash_reservations_are_serialized(sim):
    from concurrent.futures import ThreadPoolExecutor

    quote(sim)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(buy, sim, name, 100) for name in ("parallel-a", "parallel-b")]
        results = [f.result() for f in futures]
    assert sorted(r["status"] for r in results) == ["ACCEPTED", "REJECTED"]
    assert state(sim)["reconciliation"]["status"] == "MATCH"


def test_malformed_journal_fails_closed(sim):
    with sim[0].begin() as db:
        row = db.scalar(select(PaperJournal))
        row.payload = {}
    assert run(sim, "tick", Command(command_id="do-not-apply"))["status"] == "BLOCKED"


def test_clock_regression_blocks_new_mutations(sim):
    quote(sim, seconds=3)
    with pytest.raises(ValueError, match="clock moved backwards"):
        run(sim, "tick", Command(command_id="backwards"), 2)


def test_risk_limits_are_revalidated_after_losses(client):
    from packages.schemas.controls import ControlPolicy

    sessions = sessionmaker(client.app.state.engine, expire_on_commit=False)
    now = datetime(2026, 10, 31, 12, tzinfo=UTC)
    with sessions.begin() as db:
        engine.open_account(
            db,
            OpenAccount(
                account_id="paper-test",
                universe={"SYNTH": "technology"},
                policy=ControlPolicy(
                    max_daily_loss="0.001", max_drawdown="0.005", consecutive_loss_limit=1
                ),
            ),
            "operator",
            now,
        )
    sim = sessions, now
    quote(sim)
    order = buy(sim, quantity=100)["order_id"]
    q = quote(sim, "q2", 1)
    fill(sim, order, q)
    sell = run(
        sim,
        "order",
        OrderRequest(command_id="loss-exit", symbol="SYNTH", side="SELL", quantity=100),
        2,
    )["order_id"]
    q = quote(sim, "q3", 3, bid="90", ask="91")
    fill(sim, sell, q, "loss", 3)
    result = run(
        sim,
        "order",
        OrderRequest(
            command_id="blocked-entry", symbol="SYNTH", side="BUY", quantity=1, stop_price="85"
        ),
        4,
    )
    assert result["status"] == "REJECTED"
    assert {"DAILY_LOSS_LIMIT", "DRAWDOWN_LIMIT", "CONSECUTIVE_LOSS_COOLDOWN"} <= set(
        result["reasons"]
    )


@pytest.mark.parametrize("finish", ["fill", "cancel", "expire"])
def test_partial_exit_counts_one_loss_only_when_closed(sim, finish):
    quote(sim)
    order = buy(sim)["order_id"]
    q = quote(sim, "q2", 1)
    fill(sim, order, q)
    exit_order = run(
        sim,
        "order",
        OrderRequest(
            command_id="exit", symbol="SYNTH", side="SELL", quantity=10, expires_in_seconds=10
        ),
        2,
    )["order_id"]
    q = quote(sim, "q3", 3, bid="90", ask="91", size=3)
    assert fill(sim, exit_order, q, "part-exit", 3)["status"] == "PARTIALLY_FILLED"
    assert state(sim)["state"]["consecutive_losses"] == 0
    if finish == "fill":
        q = quote(sim, "q4", 4, bid="90", ask="91", size=100)
        fill(sim, exit_order, q, "rest-exit", 4)
    elif finish == "cancel":
        run(sim, "cancel", CancelRequest(command_id="cancel-exit", order_id=exit_order), 4)
    else:
        run(sim, "tick", Command(command_id="expire-exit"), 13)
    assert state(sim)["state"]["consecutive_losses"] == 1
    assert state(sim)["reconciliation"]["status"] == "MATCH"
