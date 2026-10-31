from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from services.controls.broker import BrokerError
from tests.controls.operations_fixtures import (
    FakeBroker,
    asset,
    attestation,
    broker_facts,
    methodology,
    policy,
    risk_state,
    signal,
)

REVIEW = {"X-Controls-Reviewer-Key": "review-test"}
OPERATOR = {"X-Controls-Operator-Key": "operator-test"}
BROKER = {"X-Controls-Broker-Key": "broker-test"}
ANALYSIS = {"X-Analysis-Key": "analysis-test"}
READ = {"Authorization": "Bearer dashboard-test"}


@pytest.fixture
def api_overrides():
    return {
        "controls_reviewer_key": "review-test",
        "controls_operator_key": "operator-test",
        "controls_broker_key": "broker-test",
        "controls_reviewer_identity": "qualified-test-reviewer",
        "controls_operator_identity": "test-risk-operator",
    }


def post(client, path, body, headers=REVIEW):
    response = client.post("/api/v1/controls/" + path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def seed(client, fake=None):
    fake = fake or FakeBroker()
    client.app.state.controls_broker_factory = lambda: fake
    post(client, "reviews/methodologies", methodology())
    post(client, "reviews/assets", asset())
    post(client, "reviews/policies", policy())
    post(client, "broker/refresh", {"refresh_id": "broker-1"}, BROKER)
    post(client, "quotes/refresh", {"refresh_id": "quote-1", "symbol": "AAPL"}, BROKER)
    post(client, "reviews/risk-reconciliations", risk_state())
    response = client.post(
        "/api/v1/webhooks/tradingview", json=signal(), headers={"X-Webhook-Key": "webhook-test"}
    )
    assert response.status_code == 200, response.text
    return fake


def check(client, name="check-1", signal_id="signal-ops-1", **extra):
    return post(
        client,
        "check",
        {
            "check_id": name,
            "account_id": "acct-fixture",
            "signal_id": signal_id,
            "stop_price": "95",
            **extra,
        },
        ANALYSIS,
    )


def test_review_roles_cannot_be_replaced_by_analysis_data_or_operator(client):
    for key in [ANALYSIS, OPERATOR, BROKER, {}, {"X-Data-Key": "data-test"}]:
        assert (
            client.post(
                "/api/v1/controls/reviews/methodologies", json=methodology(), headers=key
            ).status_code
            == 401
        )
    result = post(client, "reviews/methodologies", methodology())
    assert not result["authorized"]


def test_review_append_replay_conflict_and_server_receipt(client):
    body = methodology()
    body["evidence"]["recorded_at"] = "2020-01-01T00:00:00Z"
    body["evidence"]["observed_at"] = "2019-01-01T00:00:00Z"
    result = post(client, "reviews/methodologies", body)
    assert not result["duplicate"]
    assert post(client, "reviews/methodologies", body)["duplicate"]
    changed = deepcopy(body)
    changed["maximum_debt_ratio"] = "0.2"
    assert (
        client.post(
            "/api/v1/controls/reviews/methodologies", json=changed, headers=REVIEW
        ).status_code
        == 409
    )
    items = client.get(
        "/api/v1/controls/history",
        params={"kind": "methodology", "scope": "method-v1"},
        headers=READ,
    ).json()["items"]
    assert len(items) == 1 and items[0]["actor"] == "qualified-test-reviewer"
    assert (
        datetime.fromisoformat(items[0]["payload"]["evidence"]["recorded_at"]).year
        == datetime.now(UTC).year
    )
    old = client.get(
        "/api/v1/controls/history",
        params={"kind": "methodology", "scope": "method-v1", "as_of": "2020-01-01T00:00:00Z"},
        headers=READ,
    ).json()
    assert old["items"] == []


def test_stock_ratios_and_asset_checks_cannot_be_approved_by_status_alone(client):
    post(client, "reviews/methodologies", methodology())
    for changed in ["ratios", "denominator", "activity", "instrument"]:
        body = asset(record_id="asset-" + changed)
        if changed == "ratios":
            body["financials"]["debt"] = "300"
        if changed == "denominator":
            body["financials"]["denominator"] = "average_market_cap"
        if changed == "activity":
            body["assessment"]["business_activity_pass"] = False
        if changed == "instrument":
            body["instrument"]["kind"] = "cfd"
        assert (
            client.post("/api/v1/controls/reviews/assets", json=body, headers=REVIEW).status_code
            == 422
        )
    post(client, "reviews/assets", asset())


def test_server_check_reserves_exact_capacity_and_never_authorizes(client):
    seed(client)
    result = check(client)
    assert result["research_controls_pass"], result
    assert result["quantity"] == "10" and not result["authorized"]
    assert result["reservation"]["simulation_only"]
    assert check(client)["duplicate"]
    assert (
        client.post(
            "/api/v1/controls/check",
            json={
                "check_id": "check-1",
                "account_id": "acct-fixture",
                "signal_id": "signal-ops-1",
                "stop_price": "96",
            },
            headers=ANALYSIS,
        ).status_code
        == 409
    )
    second = check(client, "check-2")
    assert not second["research_controls_pass"]
    assert not second["authorized"]


def test_new_signal_ids_cannot_concurrently_overreserve_shared_capacity(client):
    seed(client)
    client.post(
        "/api/v1/webhooks/tradingview",
        json=signal("signal-ops-2"),
        headers={"X-Webhook-Key": "webhook-test"},
    )

    def run(args):
        name, sig = args
        return check(client, name, sig, quantity="6")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(run, [("concurrent-1", "signal-ops-1"), ("concurrent-2", "signal-ops-2")])
        )
    assert sum(r["research_controls_pass"] for r in results) == 1
    assert sum(int(r["quantity"]) for r in results) == 6


def test_operator_can_engage_but_only_reviewer_can_clear_kill_switch(client):
    seed(client)
    body = dict(**attestation(), record_id="kill-on", account_id="acct-fixture")
    post(client, "kill-switch/engage", body, OPERATOR)
    assert "KILL_SWITCH_ACTIVE" in check(client)["blockers"]
    body["record_id"] = "kill-off"
    assert (
        client.post("/api/v1/controls/kill-switch/clear", json=body, headers=OPERATOR).status_code
        == 401
    )
    post(client, "kill-switch/clear", body, REVIEW)
    assert check(client, "after-clear")["research_controls_pass"]


def test_rejected_revision_does_not_fall_back_to_older_approval(client):
    seed(client)
    post(client, "reviews/assets", asset(record_id="asset-revoked", status="REJECTED"))
    result = check(client)
    assert not result["research_controls_pass"]
    assert "ASSET_REJECTED" in result["blockers"]


def test_expired_latest_risk_state_does_not_fall_back(client):
    seed(client)
    body = risk_state("risk-expired")
    now = datetime.now(UTC)
    body["evidence"].update(
        effective_at=(now - timedelta(hours=2)).isoformat(),
        expires_at=(now - timedelta(seconds=1)).isoformat(),
    )
    post(client, "reviews/risk-reconciliations", body)
    assert "CURRENT_RISK_RECONCILIATION_MISSING" in check(client)["blockers"]


def test_changed_broker_activity_invalidates_reviewed_loss_state(client):
    seed(client)
    facts = broker_facts()
    facts["activity_sha256"] = "e" * 64
    client.app.state.controls_broker_factory = lambda: FakeBroker(facts)
    post(client, "broker/refresh", {"refresh_id": "broker-changed"}, BROKER)
    assert "RISK_HISTORY_UNRECONCILED" in check(client)["blockers"]


def test_failed_new_poll_blocks_old_fresh_broker_snapshot_and_cannot_recall(client):
    seed(client)

    class Failed(FakeBroker):
        def account(self):
            self.calls.append("account")
            raise BrokerError("BROKER_READ_REJECTED")

    failed = Failed()
    client.app.state.controls_broker_factory = lambda: failed
    response = post(client, "broker/refresh", {"refresh_id": "failed"}, BROKER)
    assert response["status"] == "FAILED"
    assert post(client, "broker/refresh", {"refresh_id": "failed"}, BROKER)["duplicate"]
    assert failed.calls == ["account"]
    assert "CURRENT_BROKER_CAPTURE_MISSING" in check(client)["blockers"]


def test_real_alpaca_cash_unverified_flags_fail_closed_even_with_reviews(client):
    facts = broker_facts()
    facts.update(
        cash_account_verified=False,
        settled_cash_verified=False,
        settled_cash=None,
        lending_disabled_verified=False,
        borrowing_disabled_verified=False,
    )
    seed(client, FakeBroker(facts))
    result = check(client)
    assert "CASH_ACCOUNT_OR_SETTLED_CASH_UNVERIFIED" in result["blockers"]
    assert not result["research_controls_pass"]


def test_release_is_audited_and_frees_only_research_hold(client):
    seed(client)
    check(client)
    body = {
        "release_id": "release-1",
        "reservation_id": "check-1",
        "reason": "Cancel hypothetical candidate; no broker order exists",
    }
    post(client, "reservations/release", body, OPERATOR)
    assert post(client, "reservations/release", body, OPERATOR)["duplicate"]
    assert check(client, "after-release")["research_controls_pass"]


def test_owned_exit_bypasses_entry_kill_compliance_and_cash_guards(client):
    facts = broker_facts()
    facts["cash_account_verified"] = False
    facts["positions"] = [
        {
            "symbol": "AAPL",
            "asset_id": "asset-a",
            "quantity": "10",
            "available_quantity": "8",
            "market_value": "1000",
        }
    ]
    seed(client, FakeBroker(facts))
    post(client, "reviews/assets", asset(record_id="noncompliant", status="REJECTED"))
    post(
        client,
        "kill-switch/engage",
        dict(**attestation(), record_id="kill-1", account_id="acct-fixture"),
        OPERATOR,
    )
    client.post(
        "/api/v1/webhooks/tradingview",
        json=signal("exit-signal", "EXIT_CANDIDATE"),
        headers={"X-Webhook-Key": "webhook-test"},
    )
    result = check(client, "exit-check", "exit-signal", quantity="5")
    assert result["research_controls_pass"] and not result["authorized"]
    assert result["detail"]["compliance_divestment_review_required"]
    other = check(client, "exit-other", "exit-signal", quantity="4")
    assert not other["research_controls_pass"]
    assert "INSUFFICIENT_SELLABLE_QUANTITY" in other["blockers"]


def test_main_decision_revalidates_matching_owned_check_and_rejects_unbound_ids(client):
    facts = broker_facts()
    facts["positions"] = [
        {
            "symbol": "AAPL",
            "asset_id": "asset-a",
            "quantity": "10",
            "available_quantity": "8",
            "market_value": "1000",
        }
    ]
    seed(client, FakeBroker(facts))
    client.post(
        "/api/v1/webhooks/tradingview",
        json=signal("exit-signal", "EXIT_CANDIDATE"),
        headers={"X-Webhook-Key": "webhook-test"},
    )
    check(client, "exit-check", "exit-signal", quantity="5")
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-owned",
            "signal_id": "exit-signal",
            "score": 0.8,
            "control_check_id": "exit-check",
        },
        headers=ANALYSIS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "EXIT_CANDIDATE" and not response.json()["authorized"]
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-mismatch",
            "signal_id": "signal-ops-1",
            "score": 0.8,
            "control_check_id": "exit-check",
        },
        headers=ANALYSIS,
    )
    assert response.status_code == 422


def test_main_entry_keeps_market_data_gate_and_revalidates_own_reserved_quantity(client):
    seed(client)
    check(client)
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-entry",
            "signal_id": "signal-ops-1",
            "score": 0.8,
            "control_check_id": "check-1",
        },
        headers=ANALYSIS,
    )
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["snapshot"]["controls"]["research_controls_pass"]
    assert view["snapshot"]["trusted_state"]["risk_limits_allow_entry"] is True
    assert view["status"] == "WAIT_DATA" and not view["authorized"]
    post(
        client,
        "kill-switch/engage",
        dict(**attestation(), record_id="kill-eval", account_id="acct-fixture"),
        OPERATOR,
    )
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-after-kill",
            "signal_id": "signal-ops-1",
            "score": 0.8,
            "control_check_id": "check-1",
        },
        headers=ANALYSIS,
    )
    assert not response.json()["snapshot"]["controls"]["research_controls_pass"]
    assert "KILL_SWITCH_ACTIVE" in response.json()["snapshot"]["controls"]["blockers"]


def test_expired_hold_replay_never_renews_or_clears_current_validation(client):
    seed(client)
    first = check(client)
    from sqlalchemy.orm import Session

    from apps.api.db import ControlReservation

    with Session(client.app.state.engine) as session, session.begin():
        row = session.get(ControlReservation, "check-1")
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    replay = check(client)
    assert replay["duplicate"] and not replay["reservation_active_now"]
    assert replay["reservation"]["expires_at"] == first["reservation"]["expires_at"]
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-expired",
            "signal_id": "signal-ops-1",
            "score": 0.8,
            "control_check_id": "check-1",
        },
        headers=ANALYSIS,
    )
    assert (
        "CONTROL_RESERVATION_MISSING_OR_EXPIRED"
        in response.json()["snapshot"]["controls"]["blockers"]
    )


def test_open_risk_unknown_and_market_pending_orders_fail_closed(client):
    facts = broker_facts()
    facts["positions"] = [
        {
            "symbol": "AAPL",
            "asset_id": "asset-a",
            "quantity": "1",
            "available_quantity": "1",
            "market_value": "100",
        }
    ]
    seed(client, FakeBroker(facts))
    result = check(client)
    assert "POSITION_RISK_UNKNOWN" in result["blockers"]
    facts = broker_facts()
    facts["orders"] = [
        {
            "id": "market-buy",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "type": "market",
            "asset_class": "us_equity",
            "status": "new",
            "limit_price": None,
            "stop_price": None,
            "legs": [],
        }
    ]
    client.app.state.controls_broker_factory = lambda: FakeBroker(facts)
    post(client, "broker/refresh", {"refresh_id": "broker-market"}, BROKER)
    assert "PENDING_BUY_PRICE_UNBOUNDED" in check(client, "check-market")["blockers"]


def test_new_methodology_and_wrong_scope_references_block_current_approval(client):
    seed(client)
    # Wrong check-to-signal binding is rejected, not borrowed across callers' signals.
    client.post(
        "/api/v1/webhooks/tradingview",
        json=signal("another-signal"),
        headers={"X-Webhook-Key": "webhook-test"},
    )
    check(client)
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-wrong-check",
            "signal_id": "another-signal",
            "score": 0.8,
            "control_check_id": "check-1",
        },
        headers=ANALYSIS,
    )
    assert response.status_code == 422


def test_reviewer_identity_and_distinct_keys_are_required():
    from pydantic import ValidationError

    from packages.config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(analysis_api_key="same", controls_reviewer_key="same", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(controls_broker_key="same", controls_operator_key="same", _env_file=None)


def test_owned_noncompliance_change_creates_audited_review_not_automatic_sale(client):
    facts = broker_facts()
    facts["positions"] = [
        {
            "symbol": "AAPL",
            "asset_id": "asset-a",
            "quantity": "10",
            "available_quantity": "10",
            "market_value": "1000",
        }
    ]
    seed(client, FakeBroker(facts))
    post(client, "reviews/assets", asset(record_id="asset-divestment", status="REJECTED"))
    view = client.get(
        "/api/v1/controls/history",
        params={"scope": "acct-fixture", "kind": "divestment"},
        headers=READ,
    )
    assert view.status_code == 200, view.text
    items = view.json()["items"]
    assert len(items) == 1 and items[0]["payload"]["status"] == "REVIEW_REQUIRED"
    assert items[0]["payload"]["asset_record_id"] == "asset-divestment"
    assert not items[0]["payload"]["automatic_liquidation"]


def test_server_loss_and_cooldown_reconciliation_guard(client):
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from services.notifications.models import Destination, Outbox, User

    seed(client)
    sessions = sessionmaker(client.app.state.engine)
    with sessions.begin() as db:
        db.add(
            User(
                id="risk-subscriber",
                email="risk@example.test",
                password="",
                role="viewer",
                enabled=True,
            )
        )
        db.add(
            Destination(
                id="risk-destination",
                user_id="risk-subscriber",
                chat_id="1234",
                enabled=True,
                language="en",
                kinds=["risk_stop"],
            )
        )
    body = risk_state("risk-loss")
    body["realized_pnl_today"] = "-200"
    post(client, "reviews/risk-reconciliations", body)
    assert "DAILY_LOSS_LIMIT" in check(client)["blockers"]
    body = risk_state("risk-cooldown")
    body["consecutive_losses"] = 3
    body["last_loss_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    post(client, "reviews/risk-reconciliations", body)
    assert "CONSECUTIVE_LOSS_COOLDOWN" in check(client, "cooldown-check")["blockers"]
    check(client, "cooldown-check")  # Replay cannot enqueue another alert.
    with sessions() as db:
        alerts = db.scalars(select(Outbox)).all()
        assert len(alerts) == 2 and all(a.kind == "risk_stop" for a in alerts)
        assert any("DAILY_LOSS_LIMIT" in a.text for a in alerts)
        assert any("CONSECUTIVE_LOSS_COOLDOWN" in a.text for a in alerts)


def test_stored_policy_and_kill_state_survive_new_api_instance(client):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app
    from packages.config.settings import Settings

    seed(client)
    post(
        client,
        "kill-switch/engage",
        dict(**attestation(), record_id="kill-persisted", account_id="acct-fixture"),
        OPERATOR,
    )
    app = create_app(
        Settings(
            database_url=client.app.state.engine.url.render_as_string(hide_password=False),
            dashboard_api_key="dashboard-test",
            analysis_api_key="analysis-test",
            _env_file=None,
        )
    )
    try:
        with TestClient(app) as second:
            result = check(second, "restart-check")
            assert "KILL_SWITCH_ACTIVE" in result["blockers"]
            assert result["references"]["policy"] == "policy-v1"
    finally:
        app.state.engine.dispose()


@pytest.mark.parametrize("change", ["status", "symbol", "quantity"])
def test_invalid_nested_pending_stop_never_becomes_known_risk(client, change):
    facts = broker_facts()
    stop = {
        "id": "child-stop",
        "symbol": "AAPL",
        "side": "SELL",
        "quantity": "2",
        "type": "stop",
        "asset_class": "us_equity",
        "status": "new",
        "limit_price": None,
        "stop_price": "95",
        "legs": [],
    }
    if change == "status":
        stop["status"] = "canceled"
    if change == "symbol":
        stop["symbol"] = "OTHER"
    if change == "quantity":
        stop["quantity"] = "1"
    facts["orders"] = [
        {
            "id": "buy-parent",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "2",
            "type": "limit",
            "asset_class": "us_equity",
            "status": "new",
            "limit_price": "100",
            "stop_price": None,
            "legs": [stop],
        }
    ]
    seed(client, FakeBroker(facts))
    result = check(client)
    assert "RESERVED_RISK_UNKNOWN" in result["blockers"]


@pytest.mark.parametrize("fault", ["symbol", "side"])
def test_foreign_child_stop_does_not_cover_owned_position(client, fault):
    facts = broker_facts()
    facts["positions"] = [
        {
            "symbol": "AAPL",
            "asset_id": "asset-a",
            "quantity": "2",
            "available_quantity": "0",
            "market_value": "200",
        }
    ]
    stop = {
        "id": "stop-other",
        "symbol": "OTHER",
        "side": "SELL",
        "quantity": "2",
        "type": "stop",
        "asset_class": "us_equity",
        "status": "new",
        "limit_price": None,
        "stop_price": "95",
        "legs": [],
    }
    if fault == "side":
        stop.update(symbol="AAPL", side="BUY")
    facts["orders"] = [
        {
            "id": "sell-parent",
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": "2",
            "type": "limit",
            "asset_class": "us_equity",
            "status": "new",
            "limit_price": "110",
            "stop_price": None,
            "legs": [stop],
        }
    ]
    seed(client, FakeBroker(facts))
    assert "POSITION_RISK_UNKNOWN" in check(client)["blockers"]


def test_operational_loss_day_cannot_claim_a_different_capture_timezone(client):
    request = policy()
    request["policy"]["loss_day_timezone"] = "UTC"
    response = client.post("/api/v1/controls/reviews/policies", json=request, headers=REVIEW)
    assert response.status_code == 422
    facts = broker_facts()
    facts["activity_trading_day"] = "2020-01-01"
    seed(client, FakeBroker(facts))
    assert "BROKER_ACTIVITY_DAY_MISMATCH" in check(client)["blockers"]


def test_methodology_withdrawal_invalidates_existing_asset_and_reservation(client):
    seed(client)
    check(client)
    request = methodology("method-withdrawn")
    request["status"] = "REVOKED"
    post(client, "reviews/methodologies", request)
    response = client.post(
        "/api/v1/decisions/evaluate",
        json={
            "evaluation_id": "eval-method-withdrawn",
            "signal_id": "signal-ops-1",
            "score": 0.8,
            "control_check_id": "check-1",
        },
        headers=ANALYSIS,
    )
    assert response.status_code == 200, response.text
    assert (
        "METHODOLOGY_REVIEW_CHANGED_OR_UNAVAILABLE"
        in response.json()["snapshot"]["controls"]["blockers"]
    )
    request = asset(record_id="attempt-after-method-withdrawal")
    assert (
        client.post("/api/v1/controls/reviews/assets", json=request, headers=REVIEW).status_code
        == 422
    )


@pytest.mark.parametrize("case", ["unsupported_asset", "unowned_sell"])
def test_pending_forbidden_or_unowned_orders_block_new_risk(client, case):
    facts = broker_facts()
    facts["orders"] = [
        {
            "id": "pending-forbidden",
            "symbol": "AAPL",
            "side": "SELL" if case == "unowned_sell" else "BUY",
            "quantity": "1",
            "type": "limit",
            "status": "new",
            "asset_class": "us_equity" if case == "unowned_sell" else "us_option",
            "limit_price": "100",
            "stop_price": None,
            "legs": [],
        }
    ]
    seed(client, FakeBroker(facts))
    codes = check(client)["blockers"]
    assert (
        "UNOWNED_OR_OVERSUBSCRIBED_SELL_ORDER"
        if case == "unowned_sell"
        else "UNSUPPORTED_OR_UNKNOWN_BROKER_ORDER"
    ) in codes


def test_future_effective_review_does_not_replace_current_asset_early(client):
    seed(client)
    request = asset(record_id="scheduled-asset")
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    request["assessment"]["evidence"]["effective_at"] = future
    request["instrument"]["evidence"]["effective_at"] = future
    post(client, "reviews/assets", request)
    result = check(client)
    assert result["references"]["asset"] == "asset-v1"


def test_migration_loss_never_recreates_approval_or_reservation_on_replay(client):
    from alembic import command
    from alembic.config import Config

    seed(client)
    check(client)
    config = Config("alembic.ini")
    command.downgrade(config, "0005_feed_coverage")
    assert client.get("/health/ready").status_code == 503
    command.upgrade(config, "head")
    assert client.get("/health/ready").status_code == 200
    result = check(client)
    assert not result["research_controls_pass"] and result["quantity"] == "0"
    assert "CURRENT_REVIEWED_POLICY_MISSING" in result["blockers"]
    assert "CURRENT_BROKER_CAPTURE_MISSING" in result["blockers"]


def test_prelock_clock_cannot_hide_a_competitor_reservation(client):
    from sqlalchemy.orm import Session

    from packages.config.settings import Settings
    from packages.schemas.control_operations import ControlCheck
    from services.controls.store import check_and_reserve

    seed(client)
    client.post(
        "/api/v1/webhooks/tradingview",
        json=signal("signal-competitor"),
        headers={"X-Webhook-Key": "webhook-test"},
    )
    first = check(client, "reserved-first", quantity="6")
    stale_prelock = datetime.fromisoformat(first["as_of"]) - timedelta(microseconds=1)
    request = ControlCheck(
        check_id="reserved-after-wait",
        account_id="acct-fixture",
        signal_id="signal-competitor",
        stop_price="95",
        quantity="6",
    )
    with Session(client.app.state.engine) as session, session.begin():
        result = check_and_reserve(session, request, stale_prelock, Settings(_env_file=None))
    assert not result["research_controls_pass"]
    assert "REQUESTED_QUANTITY_EXCEEDS_CAPACITY" in result["blockers"]


def test_linked_decision_refreshes_prelock_clock_after_kill_change(client):
    from sqlalchemy.orm import Session

    from packages.config.settings import Settings
    from packages.schemas.intelligence import EvaluationRequest
    from services.decision_engine.store import store_evaluation

    seed(client)
    first = check(client)
    stale_prelock = datetime.fromisoformat(first["as_of"]) + timedelta(microseconds=1)
    post(
        client,
        "kill-switch/engage",
        dict(**attestation(), record_id="kill-after-call-clock", account_id="acct-fixture"),
        OPERATOR,
    )
    request = EvaluationRequest(
        evaluation_id="decision-after-lock-wait",
        signal_id="signal-ops-1",
        score=0.8,
        control_check_id="check-1",
    )
    with Session(client.app.state.engine) as session, session.begin():
        result = store_evaluation(session, request, stale_prelock, Settings(_env_file=None))
    assert not result["snapshot"]["controls"]["research_controls_pass"]
    assert "KILL_SWITCH_ACTIVE" in result["snapshot"]["controls"]["blockers"]


def test_backend_rejects_approved_asset_missing_the_new_liquidity_input(client):
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from apps.api.db import ControlRevision
    from tests.controls.test_assets_methodology import assets_method

    method = assets_method().model_dump(mode="json")
    assert (
        client.post(
            "/api/v1/controls/reviews/methodologies", json=method, headers=REVIEW
        ).status_code
        == 200
    )
    body = asset()
    assert (
        client.post("/api/v1/controls/reviews/assets", json=body, headers=REVIEW).status_code == 422
    )
    body["financials"]["receivables_cash"] = "500"
    assert (
        client.post("/api/v1/controls/reviews/assets", json=body, headers=REVIEW).status_code == 422
    )
    with sessionmaker(client.app.state.engine)() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ControlRevision)
                .where(ControlRevision.kind == "asset")
            )
            == 0
        )
    body["financials"]["receivables_cash"] = "100"
    body["financials"]["impure_revenue"] = "5"
    assert (
        client.post("/api/v1/controls/reviews/assets", json=body, headers=REVIEW).status_code == 200
    )
