from datetime import timedelta

import pytest

from apps.api.db import ControlRevision, DecisionRecord
from services.notifications.models import User
from services.paper import forward, runner
from services.paper.models import PaperAccount, PaperRun
from services.paper.schemas import DecisionOrder, ReviewRun
from tests.paper.forward_fixtures import bundle, seed_decision


def prepared(env, monkeypatch):
    intelligence = seed_decision(env, monkeypatch)
    sessions, now, *_ = env
    claim = runner.claim(sessions, "run-test", "one", now)
    runner.process(sessions, "run-test", "one", claim, bundle(now), now)
    with sessions() as db:
        account = db.get(PaperAccount, "forward-test")
        request = {
            "symbol": "AAPL",
            "quantity": 1,
            "stop_price": "95",
            "decision_id": "decision-test",
        }
        assert forward.entry_guard(db, account, request, now) == []
    return intelligence, request


@pytest.mark.parametrize(
    "change,reason",
    [
        ("decision", "FRESH_STORED_DECISION_REQUIRED"),
        ("policy", "CURRENT_REVIEWED_PAPER_POLICY_REQUIRED"),
        ("asset", "CURRENT_ASSET_REVIEW_REQUIRED"),
        ("method", "METHODOLOGY_REVIEW_CHANGED_OR_EXPIRED"),
        ("reviewer", "FORWARD_PROTOCOL_UNAVAILABLE"),
        ("score", "PAPER_SCORE_BELOW_THRESHOLD"),
    ],
)
def test_decision_and_current_reviews_rechecked_at_fill(forward_env, monkeypatch, change, reason):
    _, request = prepared(forward_env, monkeypatch)
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        if change == "decision":
            db.get(DecisionRecord, "decision-test").created_at = now - timedelta(hours=1)
        elif change == "score":
            row = db.get(DecisionRecord, "decision-test")
            row.response = row.response | {"snapshot": row.response["snapshot"] | {"score": 0.1}}
        elif change == "reviewer":
            db.get(User, "paper-reviewer").enabled = False
        else:
            key = {"policy": "paper-policy", "asset": "asset-v1", "method": "method-v1"}[change]
            row = db.scalar(forward.select(ControlRevision).where(ControlRevision.record_id == key))
            row.expires_at = now
    with sessions() as db:
        assert reason in forward.entry_guard(db, db.get(PaperAccount, "forward-test"), request, now)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("event", "PAPER_EVENT_OR_ASSESSMENT_RESTRICTION"),
        ("assessment", "PAPER_EVENT_OR_ASSESSMENT_RESTRICTION"),
        ("coverage", "PAPER_SOURCE_SCOPE_NOT_REVIEWED"),
        ("unclassified", "PAPER_INTELLIGENCE_COVERAGE_UNAVAILABLE"),
        ("corporate", "CORPORATE_ACTION_COVERAGE_REQUIRED"),
    ],
)
def test_source_assumptions_never_clear_missing_data_or_event_blocks(
    forward_env, monkeypatch, change, reason
):
    intelligence, request = prepared(forward_env, monkeypatch)
    if change == "event":
        intelligence["event_restrictions"] = [{"code": "FOMC_WINDOW"}]
    elif change == "assessment":
        intelligence["assessment_restrictions"] = [{"code": "RESTRICT"}]
    elif change == "coverage":
        intelligence["feeds"]["news"]["required_feed_available"] = False
    elif change == "unclassified":
        intelligence["feed_blockers"].append({"code": "UNCLASSIFIED_NEWS"})
    else:
        monkeypatch.setattr(
            forward, "coverage_status", lambda *args: {"required_feed_available": False}
        )
    sessions, now, *_ = forward_env
    with sessions() as db:
        assert reason in forward.entry_guard(db, db.get(PaperAccount, "forward-test"), request, now)


def test_operator_cannot_review_own_protocol_or_a_changed_hash(forward_env):
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {"status": "PENDING_REVIEW"}
        body = ReviewRun(
            protocol_sha256=forward.protocol_hash(run),
            approved=True,
            expires_at=now + timedelta(days=30),
            note="Isolated technical protocol review fixture",
        )
    with pytest.raises(ValueError, match="distinct enabled reviewer"), sessions.begin() as db:
        forward.review(db, "run-test", body, "paper-operator", now)
    with pytest.raises(forward.ImportConflict, match="exact protocol hash"), sessions.begin() as db:
        forward.review(
            db,
            "run-test",
            body.model_copy(update={"protocol_sha256": "f" * 64}),
            "paper-reviewer",
            now,
        )


def test_expired_entry_review_does_not_stop_owned_exit_worker(forward_env):
    sessions, now, *_ = forward_env
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {"review_expires_at": now.isoformat()}
    runner.claim(sessions, "run-test", "one", now)
    with sessions() as db, pytest.raises(ValueError, match="expired"):
        forward.approved_run(db, db.get(PaperAccount, "forward-test"), now)


def test_bridge_replay_cannot_turn_same_decision_into_two_orders(forward_env, monkeypatch):
    prepared(forward_env, monkeypatch)
    sessions, now, *_ = forward_env
    body = DecisionOrder(decision_id="decision-test", quantity=1, stop_price="95")
    with sessions.begin() as db:
        result = forward.decision_order(db, "forward-test", body, "paper-operator", now)
        assert result["duplicate"]
    with pytest.raises(forward.ImportConflict), sessions.begin() as db:
        forward.decision_order(
            db, "forward-test", body.model_copy(update={"quantity": 2}), "paper-operator", now
        )


def test_review_expiring_during_validation_cannot_authorize_a_fill(forward_env, monkeypatch):
    from services.paper import engine
    from services.paper.schemas import FillRequest

    env = forward_env
    prepared(env, monkeypatch)
    sessions, now, *_ = env
    later = now + timedelta(seconds=60)
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        run.state = run.state | {"review_expires_at": (later + timedelta(seconds=1)).isoformat()}
    with sessions.begin() as db:
        q = engine.mutate(
            db,
            "forward-test",
            "quote",
            bundle(later).quotes["AAPL"],
            "paper-worker",
            later,
            authority=engine.WORKER_AUTHORITY,
        )["quote_id"]
    original = engine.entry_check

    def slow_check(db, account, request, quantity, cap, at, exclude=None):
        result = original(db, account, request, quantity, cap, at, exclude)
        db.info["paper_clock"] = lambda: later + timedelta(seconds=3)
        return result

    monkeypatch.setattr(engine, "entry_check", slow_check)
    with sessions.begin() as db:
        order = engine.orders(db, "forward-test")[0]
        result = engine.mutate(
            db,
            "forward-test",
            "fill",
            FillRequest(command_id="late-review-fill", order_id=order.id, quote_id=q),
            "paper-worker",
            later,
            authority=engine.WORKER_AUTHORITY,
        )
        assert (
            result["status"] == "NO_FILL"
            and result["reason"] == "ENTRY_EVIDENCE_EXPIRED_BEFORE_COMMIT"
        )
