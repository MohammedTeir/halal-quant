"""Fictional protocols/data/reviews; no production provider or qualified approval."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from apps.api.db import ControlRevision, DecisionRecord, SignalRecord
from packages.schemas.controls import ControlPolicy
from packages.schemas.signals import Signal
from services.notifications.models import User
from services.paper import engine, forward
from services.paper.models import PaperRun
from services.paper.provider import MarketBundle, MarketSession
from services.paper.schemas import ForwardProtocol, OpenAccount, QuoteRequest, ReviewRun
from tests.controls.operations_fixtures import asset


@pytest.fixture
def forward_env(client):
    sessions = sessionmaker(client.app.state.engine, expire_on_commit=False)
    now = datetime(2026, 11, 2, 14, 30, 10, tzinfo=UTC)
    cfg = OpenAccount(
        account_id="forward-test",
        mode="forward",
        universe={"AAPL": "technology"},
        policy=ControlPolicy(version="paper-policy", methodology="method-v1"),
    )
    providers = {
        k: k + "-fixture" for k in ("news", "calendar", "fomc", "earnings", "corporate_actions")
    }
    protocol = ForwardProtocol(
        run_id="run-test",
        account_id="forward-test",
        feed_providers=providers,
        data_review={p: "a" * 64 for p in ["alpaca_iex", *providers.values()]},
        source_limitations="Fictional source reviews for isolated software tests only",
        references=["https://example.invalid/paper-fixture"],
    )
    with sessions.begin() as db:
        db.add_all(
            [
                User(
                    id="paper-operator",
                    email="op@example.test",
                    password="",
                    role="operator",
                    enabled=True,
                ),
                User(
                    id="paper-reviewer",
                    email="rev@example.test",
                    password="",
                    role="reviewer",
                    enabled=True,
                ),
            ]
        )
    with sessions.begin() as db:
        engine.open_account(db, cfg, "paper-operator", now - timedelta(seconds=1))
    with sessions.begin() as db:
        forward.propose(db, protocol, "paper-operator", now)
    with sessions.begin() as db:
        run = db.get(PaperRun, "run-test")
        forward.review(
            db,
            run.id,
            ReviewRun(
                protocol_sha256=forward.protocol_hash(run),
                approved=True,
                expires_at=now + timedelta(days=89),
                note="Fictional reviewed protocol for isolated tests only",
            ),
            "paper-reviewer",
            now,
        )
    return sessions, now, cfg, protocol


def bundle(now, bid="99", ask="100", size=100, opened=True, quote_at=None):
    start = now.replace(hour=14, minute=30, second=0, microsecond=0)
    end = start + timedelta(hours=6, minutes=30)
    sessions = tuple(
        MarketSession(
            date=(start + timedelta(days=i)).date(),
            opens=start + timedelta(days=i),
            closes=end + timedelta(days=i),
        )
        for i in range(4)
    )
    receipt = forward.digest({"at": now.isoformat(), "bid": bid, "ask": ask})
    q = QuoteRequest(
        command_id="q:" + receipt,
        symbol="AAPL",
        source="alpaca_iex",
        observed_at=quote_at or now - timedelta(seconds=1),
        bid=bid,
        ask=ask,
        bid_size=size,
        ask_size=size,
        receipt_sha256=receipt,
        session_open=start,
        session_close=end,
        settlement_at=sessions[1].opens,
    )
    return MarketBundle(
        observed_at=now,
        received_at=now,
        market_open=opened,
        sessions=sessions,
        quotes={"AAPL": q} if opened else {},
        receipt_sha256=receipt,
    )


def seed_decision(env, monkeypatch):
    sessions, now, cfg, protocol = env
    asset_payload = asset()
    for name in ("assessment", "instrument"):
        asset_payload[name]["evidence"].update(
            observed_at=(now - timedelta(seconds=10)).isoformat(),
            recorded_at=(now - timedelta(seconds=9)).isoformat(),
            effective_at=(now - timedelta(seconds=10)).isoformat(),
            expires_at=(now + timedelta(days=80)).isoformat(),
        )
    asset_payload["methodology_record_id"] = "method-v1"
    signal = Signal(
        schema_version="1.0",
        event_id="paper-signal",
        strategy="adaptive_pullback",
        strategy_version="1.0.0",
        asset_class="stock",
        symbol="AAPL",
        timeframe="240",
        action="ENTRY_CANDIDATE",
        bar_time=now - timedelta(seconds=5),
        price="100",
    )
    with sessions.begin() as db:
        for kind, scope, record, payload in [
            ("methodology", "method-v1", "method-v1", {"status": "APPROVED"}),
            ("asset", "AAPL", "asset-v1", asset_payload),
            (
                "policy",
                cfg.account_id,
                "paper-policy",
                {"policy": cfg.policy.model_dump(mode="json")},
            ),
        ]:
            db.add(
                ControlRevision(
                    record_id=record,
                    kind=kind,
                    scope=scope,
                    request_sha256="a" * 64,
                    actor="paper-reviewer",
                    received_at=now - timedelta(seconds=8),
                    effective_at=now - timedelta(seconds=8),
                    expires_at=now + timedelta(days=80),
                    payload=payload,
                )
            )
        db.add(
            SignalRecord(
                event_id=signal.event_id,
                payload=signal.model_dump(mode="json"),
                received_at=now - timedelta(seconds=5),
            )
        )
        db.add(
            DecisionRecord(
                id="decision-test",
                request_sha256="b" * 64,
                signal_id=signal.event_id,
                created_at=now - timedelta(seconds=4),
                response={
                    "status": "WAIT_DATA",
                    "authorized": False,
                    "snapshot": {"score": 0.9, "signal": signal.model_dump(mode="json")},
                },
            )
        )
    intelligence = {
        "event_restrictions": [],
        "assessment_restrictions": [],
        "feed_blockers": [
            {"code": "PROVIDER_UNVERIFIED", "kind": k}
            for k in ("news", "calendar", "fomc", "earnings")
        ],
        "feeds": {
            k: {"provider": p, "required_feed_available": True}
            for k, p in protocol.feed_providers.items()
            if k != "corporate_actions"
        },
    }
    monkeypatch.setattr(forward, "intelligence_snapshot", lambda *args: intelligence)
    monkeypatch.setattr(forward, "coverage_status", lambda *args: {"required_feed_available": True})
    return intelligence
