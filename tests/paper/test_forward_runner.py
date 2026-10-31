from datetime import timedelta

import pytest

from services.notifications.models import User
from services.paper import engine, forward, runner
from services.paper.models import PaperAccount, PaperRun
from services.paper.schemas import OrderRequest
from tests.paper.forward_fixtures import bundle, seed_decision


def cycle(env, owner="worker-one", seconds=0, **kwargs):
    sessions, now, *_ = env
    now += timedelta(seconds=seconds)
    held = runner.claim(sessions, "run-test", owner, now)
    return runner.process(sessions, "run-test", owner, held, bundle(now, **kwargs), now)


def test_automatic_decision_fill_protective_exit_and_settlement_survive_restart(
    forward_env, monkeypatch
):
    env = forward_env
    seed_decision(env, monkeypatch)
    first = cycle(env)
    assert any(r.get("status") == "ACCEPTED" for r in first["results"]), first
    second = cycle(env, seconds=60)
    assert any(
        r.get("status") == "FILLED" and r.get("fill", {}).get("side") == "BUY"
        for r in second["results"]
    ), second
    third = cycle(env, seconds=120, bid="90", ask="91")
    assert any(r.get("status") == "ACCEPTED" for r in third["results"]), third
    # A restart preserves the protective order instead of replacing it forever.
    runner.release(env[0], "run-test", "worker-one")
    fourth = cycle(env, owner="worker-two", seconds=180, bid="89", ask="90")
    assert any(
        r.get("status") == "FILLED" and r.get("fill", {}).get("side") == "SELL"
        for r in fourth["results"]
    ), fourth
    with env[0]() as db:
        account = db.get(PaperAccount, "forward-test")
        assert not account.state["positions"]
        assert len(account.state["unsettled"]) == 1
        settlement = next(iter(account.state["unsettled"].values()))
        assert settlement["available_at"].startswith("2026-11-03T14:30:00")
        report = forward.report(db, db.get(PaperRun, "run-test"), env[1] + timedelta(seconds=181))
        assert report["status"] == "NOT_CONFIRMED" and report["restart_observed"]
        assert "INSUFFICIENT_ACTUAL_ELAPSED_TIME" in report["blockers"]
        assert not report["critical_violations"]
        assert report["completed_exit_orders"] == 1


def test_one_worker_lease_and_generation_fence_prevent_duplicate_matching(forward_env):
    sessions, now, *_ = forward_env
    old = runner.claim(sessions, "run-test", "old", now)
    with pytest.raises(runner.LeaseLost):
        runner.claim(sessions, "run-test", "other", now + timedelta(seconds=1))
    later = now + timedelta(seconds=181)
    new = runner.claim(sessions, "run-test", "other", later)
    assert new["generation"] == 2
    with pytest.raises(runner.LeaseLost):
        runner.process(sessions, "run-test", "old", old, bundle(later), later)


def test_duplicate_cycle_does_not_reapply_quotes_or_commands(forward_env):
    sessions, now, *_ = forward_env
    held = runner.claim(sessions, "run-test", "one", now)
    first = runner.process(sessions, "run-test", "one", held, bundle(now), now)
    second = runner.process(sessions, "run-test", "one", held, bundle(now), now)
    assert first["status"] == "OK" and second["duplicate"]
    with sessions() as db:
        assert len(engine.entries(db, "forward-test")) == 3  # open, tick, quote


def test_provider_outage_pauses_without_matching_and_recovers(forward_env):
    sessions, now, *_ = forward_env
    held = runner.claim(sessions, "run-test", "one", now)
    result = runner.problem(sessions, "run-test", "one", held, "MARKET_DATA_UNAVAILABLE", now=now)
    assert result["status"] == "PAUSED"
    assert cycle(forward_env, owner="one", seconds=60)["status"] == "OK"
    with sessions() as db:
        assert db.get(PaperAccount, "forward-test").state["positions"] == {}


def test_reconciliation_error_fails_run_and_cannot_be_reset_by_restart(forward_env):
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        account = db.get(PaperAccount, "forward-test")
        account.state = account.state | {"cash": "999999"}
    result = cycle(forward_env)
    assert result["status"] == "CRITICAL" and result["error"] == "RECONCILIATION_MISMATCH"
    with pytest.raises(ValueError, match="active forward"):
        runner.claim(sessions, "run-test", "another", now + timedelta(seconds=181))


def test_untrusted_forward_quote_order_and_fill_are_rejected(forward_env):
    sessions, now, *_ = forward_env
    with sessions.begin() as db, pytest.raises(ValueError, match="server paper worker"):
        engine.mutate(
            db,
            "forward-test",
            "order",
            OrderRequest(
                command_id="manual", symbol="AAPL", side="BUY", quantity=1, stop_price="95"
            ),
            "operator",
            now,
        )


def test_review_hash_blocks_work_but_disabled_reviewer_only_blocks_entries(forward_env):
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        reviewer = db.get(User, "paper-reviewer")
        reviewer.enabled = False
    runner.claim(sessions, "run-test", "one", now)
    with sessions() as db, pytest.raises(ValueError, match="reviewer or review"):
        forward.approved_run(db, db.get(PaperAccount, "forward-test"), now)
    with sessions.begin() as db:
        db.get(User, "paper-reviewer").enabled = True
        run = db.get(PaperRun, "run-test")
        run.protocol = run.protocol | {"quantity_per_decision": 100}
    with pytest.raises(ValueError, match="protocol changed"):
        runner.claim(sessions, "run-test", "one", now)


def test_expired_review_blocks_entry_but_standing_stop_still_sells_owned_shares(
    forward_env, monkeypatch
):
    env = forward_env
    seed_decision(env, monkeypatch)
    cycle(env)
    cycle(env, seconds=60)
    with env[0].begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {"review_expires_at": (env[1] + timedelta(seconds=61)).isoformat()}
    cycle(env, seconds=120, bid="90", ask="91")
    result = cycle(env, seconds=180, bid="90", ask="91")
    assert any(r.get("fill", {}).get("side") == "SELL" for r in result["results"])


def test_explicit_liquidation_waits_for_fresh_quote_and_exits_without_entry_approval(
    forward_env, monkeypatch
):
    from services.paper.schemas import ExitRequest

    env = forward_env
    seed_decision(env, monkeypatch)
    cycle(env)
    cycle(env, seconds=60)
    with env[0].begin() as db:
        engine.mutate(
            db,
            "forward-test",
            "liquidate",
            ExitRequest(command_id="close-owned", reason="Operator requested owned-only closeout"),
            "paper-operator",
            env[1] + timedelta(seconds=61),
        )
    cycle(env, seconds=120, bid="102", ask="103")
    result = cycle(env, seconds=180, bid="102", ask="103")
    assert any(r.get("fill", {}).get("side") == "SELL" for r in result["results"])
    with env[0]() as db:
        assert not db.get(PaperAccount, "forward-test").state["positions"]


def test_missing_quote_cancels_entries_without_reusing_old_liquidity(forward_env, monkeypatch):
    env = forward_env
    seed_decision(env, monkeypatch)
    cycle(env)
    now = env[1] + timedelta(seconds=60)
    source = bundle(now).model_copy(update={"quotes": {}, "missing_symbols": ("AAPL",)})
    held = runner.claim(env[0], "run-test", "worker-one", now)
    result = runner.process(env[0], "run-test", "worker-one", held, source, now)
    assert result["status"] == "PAUSED" and result["error"] == "PARTIAL_MARKET_DATA"
    with env[0]() as db:
        assert not db.get(PaperAccount, "forward-test").state["positions"]
        assert all(o.state["status"] not in engine.OPEN for o in engine.orders(db, "forward-test"))


def test_new_decision_for_same_signal_cannot_duplicate_entry(forward_env, monkeypatch):
    from apps.api.db import DecisionRecord
    from services.paper.schemas import DecisionOrder

    env = forward_env
    seed_decision(env, monkeypatch)
    cycle(env)
    with env[0].begin() as db:
        old = db.get(DecisionRecord, "decision-test")
        db.add(
            DecisionRecord(
                id="decision-copy",
                request_sha256="f" * 64,
                signal_id=old.signal_id,
                created_at=old.created_at,
                response=old.response,
            )
        )
    with pytest.raises(forward.ImportConflict), env[0].begin() as db:
        forward.decision_order(
            db,
            "forward-test",
            DecisionOrder(decision_id="decision-copy", quantity=1, stop_price="95"),
            "paper-operator",
            env[1],
        )
    with env[0]() as db:
        assert len(engine.orders(db, "forward-test")) == 1


def test_corporate_action_exclusion_exits_before_effective_date(forward_env, monkeypatch):
    from apps.api.db import CorporateActionRecord

    env = forward_env
    seed_decision(env, monkeypatch)
    cycle(env)
    cycle(env, seconds=60)
    with env[0].begin() as db:
        db.add(
            CorporateActionRecord(
                id="c" * 64,
                provider="corporate_actions-fixture",
                item_id="split-test",
                revision=1,
                published_at=env[1],
                received_at=env[1],
                payload={
                    "symbol": "AAPL",
                    "effective_at": (env[1] + timedelta(days=1)).isoformat(),
                    "action_type": "split",
                    "split_ratio": "2",
                },
            )
        )
    cycle(env, seconds=120, bid="101", ask="102")
    result = cycle(env, seconds=180, bid="101", ask="102")
    assert any(r.get("fill", {}).get("side") == "SELL" for r in result["results"])
    assert result["status"] == "OK"


def test_missed_split_never_uses_adjusted_price_against_old_share_quantity(
    forward_env, monkeypatch
):
    from apps.api.db import CorporateActionRecord

    env = forward_env
    seed_decision(env, monkeypatch)
    cycle(env)
    cycle(env, seconds=60)
    with env[0].begin() as db:
        db.add(
            CorporateActionRecord(
                id="d" * 64,
                provider="corporate_actions-fixture",
                item_id="late-split",
                revision=1,
                published_at=env[1] + timedelta(seconds=90),
                received_at=env[1] + timedelta(seconds=100),
                payload={
                    "symbol": "AAPL",
                    "effective_at": (env[1] + timedelta(seconds=80)).isoformat(),
                    "action_type": "split",
                    "split_ratio": "2",
                },
            )
        )
    result = cycle(env, seconds=120, bid="50", ask="51")
    assert result["status"] == "CRITICAL" and result["error"] == "CORPORATE_ACTION_MISSED_EXIT"
    with env[0]() as db:
        assert db.get(PaperAccount, "forward-test").state["positions"]["AAPL"]["mark"] == "99"


def test_lease_renewal_after_backoff_is_not_misreported_as_process_restart(forward_env):
    env = forward_env
    cycle(env, owner="same-process")
    cycle(env, owner="same-process", seconds=181)
    with env[0]() as db:
        run = db.get(PaperRun, "run-test")
        assert run.state["generation"] == 2
        result = forward.report(db, run, env[1] + timedelta(seconds=182))
    assert not result["restart_observed"]


def test_post_cycle_invariant_failure_rolls_back_every_ledger_change(forward_env, monkeypatch):
    env = forward_env
    original = engine.reconcile
    calls = 0

    def fail_final(db, account):
        nonlocal calls
        calls += 1
        return (
            {"status": "MISMATCH", "errors": ["fixture-drift"]}
            if calls == 2
            else original(db, account)
        )

    monkeypatch.setattr(engine, "reconcile", fail_final)
    held = runner.claim(env[0], "run-test", "one", env[1])
    with pytest.raises(runner.CriticalCycle):
        runner.process(env[0], "run-test", "one", held, bundle(env[1]), env[1])
    with env[0]() as db:
        assert len(engine.entries(db, "forward-test")) == 1
        assert not engine.quotes(db, "forward-test")
    failed = runner.problem(
        env[0],
        "run-test",
        "one",
        held,
        "POST_CYCLE_RECONCILIATION_MISMATCH",
        critical=True,
        now=env[1],
    )
    assert failed["status"] == "CRITICAL"


def test_lease_expiring_during_cycle_rolls_back_all_matching(forward_env, monkeypatch):
    env = forward_env
    sessions, now, *_ = env
    held = runner.claim(sessions, "run-test", "one", now)
    times = iter([now, now + timedelta(seconds=181)])
    monkeypatch.setattr(runner, "utcnow", lambda: next(times))
    monkeypatch.setattr(engine, "utcnow", lambda: now)
    with pytest.raises(runner.LeaseLost):
        runner.process(sessions, "run-test", "one", held, bundle(now))
    with sessions() as db:
        assert len(engine.entries(db, "forward-test")) == 1
        assert not engine.quotes(db, "forward-test")
