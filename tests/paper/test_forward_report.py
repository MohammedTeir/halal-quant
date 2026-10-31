from datetime import timedelta

from sqlalchemy import select

from services.paper import forward, runner
from services.paper.models import PaperCycle, PaperRun
from tests.paper.forward_fixtures import bundle


def test_no_observations_or_only_accelerated_time_cannot_pass(forward_env):
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        early = runner.finalize(db, run.id, "paper-operator", now)
        assert early["status"] == "NOT_CONFIRMED"
        assert "INSUFFICIENT_ACTUAL_ELAPSED_TIME" in early["blockers"]
        assert "INSUFFICIENT_COMPLETE_MARKET_SESSIONS" in early["blockers"]
        assert "INSUFFICIENT_COMPLETED_EXIT_ORDERS" in early["blockers"]
    with sessions() as db:
        assert db.get(PaperRun, "run-test").state["status"] == "APPROVED"


def test_partial_session_and_lease_claim_alone_do_not_prove_coverage_or_restart(forward_env):
    sessions, now, *_ = forward_env
    held = runner.claim(sessions, "run-test", "one", now)
    runner.process(sessions, "run-test", "one", held, bundle(now), now)
    runner.release(sessions, "run-test", "one")
    runner.claim(sessions, "run-test", "two", now + timedelta(seconds=60))
    with sessions() as db:
        result = forward.report(db, db.get(PaperRun, "run-test"), now + timedelta(hours=8))
    assert not result["qualifying_sessions"]
    assert not result["restart_observed"]
    assert "WORKER_STALE" in result["blockers"]


def test_corrupt_observation_chain_cannot_be_accepted(forward_env):
    sessions, now, *_ = forward_env
    held = runner.claim(sessions, "run-test", "one", now)
    runner.process(sessions, "run-test", "one", held, bundle(now), now)
    with sessions.begin() as db:
        db.scalar(select(PaperCycle)).entry_sha256 = "f" * 64
    with sessions() as db:
        result = forward.report(db, db.get(PaperRun, "run-test"), now)
    assert "CYCLE_CHAIN_MISMATCH" in result["critical_violations"]


def test_repeated_fake_exit_results_do_not_count_as_real_ledger_exits(forward_env):
    sessions, now, *_ = forward_env
    held = runner.claim(sessions, "run-test", "one", now)
    with sessions.begin() as db:
        from services.controls.store import lock_controls

        lock_controls(db)
        run = db.get(PaperRun, "run-test")
        runner.append_cycle(
            db,
            run,
            held,
            now,
            {
                "status": "OK",
                "generation": 1,
                "market_open": True,
                "session": bundle(now).sessions[0].model_dump(mode="json"),
                "results": [{"status": "FILLED", "order_id": "invented", "fill": {"side": "SELL"}}]
                * 20,
            },
        )
    with sessions() as db:
        result = forward.report(db, db.get(PaperRun, "run-test"), now)
    assert result["completed_exit_orders"] == 0
    assert "EXIT_RESULT_NOT_IN_LEDGER" in result["critical_violations"]


def test_complete_fabricated_timeline_exercises_report_and_frozen_finalization_only(
    forward_env, monkeypatch
):
    """Unit-only fabricated time/ledger. This is NEVER real forward acceptance."""
    from datetime import datetime
    from types import SimpleNamespace

    from services.paper import engine

    sessions, now, *_ = forward_env
    rows = []
    dates = []
    date = now.date()
    while len(dates) < 20:
        if date.weekday() < 5:
            dates.append(date)
        date += timedelta(days=1)
    chain = engine.ZERO_HASH
    for day_index, date in enumerate(dates):
        opens = datetime.combine(date, now.time(), tzinfo=now.tzinfo).replace(second=0)
        closes = opens + timedelta(hours=6, minutes=30)
        for tick in range(0, 23400, 180):
            at = opens + timedelta(seconds=tick + 10)
            cycle_id = forward.digest({"day": str(date), "tick": tick})
            results = (
                [
                    {"status": "FILLED", "order_id": f"exit-{i}", "fill": {"side": "SELL"}}
                    for i in range(10)
                ]
                if day_index == 19 and tick == 0
                else []
            )
            payload = {
                "status": "OK",
                "worker_id": "worker-one" if day_index < 10 else "worker-two",
                "generation": 1 if day_index < 10 else 2,
                "market_open": True,
                "session": {
                    "date": date.isoformat(),
                    "opens": opens.isoformat(),
                    "closes": closes.isoformat(),
                },
                "results": results,
                "recovery": {"verified": day_index == 10 and tick == 0},
            }
            seal = forward.cycle_seal("run-test", cycle_id, at, at, chain, payload)
            rows.append(
                SimpleNamespace(
                    id=cycle_id,
                    started_at=at,
                    completed_at=at,
                    previous_sha256=chain,
                    entry_sha256=seal,
                    payload=payload,
                )
            )
            chain = seal
    finished = closes + timedelta(seconds=10)
    exits = [
        SimpleNamespace(
            id=f"exit-{i}",
            request={"side": "SELL"},
            state={"status": "FILLED"},
            created_at=now + timedelta(seconds=1),
        )
        for i in range(10)
    ]
    monkeypatch.setattr(forward, "cycles", lambda *args: rows)
    monkeypatch.setattr(engine, "orders", lambda *args: exits)
    monkeypatch.setattr(engine, "reconcile", lambda *args: {"status": "MATCH"})
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {
            "started_at": now.isoformat(),
            "last_seen": finished.isoformat(),
            "generation": 2,
            "owner": "worker-two",
        }
    with sessions.begin() as db:
        result = runner.finalize(db, "run-test", "paper-operator", finished)
        assert result["status"] == "PASSED" and len(result["qualifying_sessions"]) == 20
    with sessions() as db:
        frozen = forward.report(db, db.get(PaperRun, "run-test"), finished + timedelta(days=1))
        assert frozen == result
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {"final_report": run.state["final_report"] | {"cycles": 999999}}
    with sessions() as db:
        assert (
            "FINAL_REPORT_HASH_MISMATCH"
            in forward.report(db, db.get(PaperRun, "run-test"), finished)["critical_violations"]
        )
