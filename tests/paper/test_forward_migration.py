from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, DateTime, Integer, String, column, select, table
from sqlalchemy.orm import sessionmaker

from services.paper.models import PaperQuote


def test_upgrade_preserves_legacy_quote_payload_and_consumption(client):
    config = Config("alembic.ini")
    command.downgrade(config, "0008_paper_simulator")
    old = table(
        "paper_quotes",
        column("id", String),
        column("account_id", String),
        column("created_at", DateTime(timezone=True)),
        column("payload", JSON),
        column("used_bid", Integer),
        column("used_ask", Integer),
    )
    payload = {
        "command_id": "legacy",
        "symbol": "AAPL",
        "source": "synthetic",
        "observed_at": "2026-10-30T14:30:00Z",
        "bid": "99",
        "ask": "100",
        "bid_size": 10,
        "ask_size": 10,
    }
    with client.app.state.engine.begin() as connection:
        connection.execute(
            old.insert().values(
                id="e" * 64,
                account_id="legacy",
                created_at=datetime(2026, 10, 30, 14, 30, tzinfo=UTC),
                payload=payload,
                used_bid=2,
                used_ask=3,
            )
        )
    command.upgrade(config, "head")
    command.check(config)
    with sessionmaker(client.app.state.engine)() as db:
        row = db.scalar(select(PaperQuote).where(PaperQuote.id == "e" * 64))
        assert row.payload == payload and row.used_bid == 2 and row.used_ask == 3
        assert row.symbol == "AAPL" and row.observed_at.hour == 14


def test_new_optional_fields_preserve_legacy_synthetic_idempotency_payloads():
    from services.paper.schemas import OpenAccount, OrderRequest, QuoteRequest

    body = OpenAccount(account_id="legacy", universe={"AAPL": "technology"}).model_dump(mode="json")
    assert set(body) == {
        "account_id",
        "mode",
        "initial_cash",
        "universe",
        "policy",
        "settlement_delay_seconds",
    }
    order = OrderRequest(
        command_id="old", symbol="AAPL", side="BUY", quantity=1, stop_price="95"
    ).model_dump(mode="json")
    assert "decision_id" not in order
    quote = QuoteRequest(
        command_id="old",
        symbol="AAPL",
        observed_at=datetime(2026, 10, 30, tzinfo=UTC),
        bid="99",
        ask="100",
        bid_size=1,
        ask_size=1,
    ).model_dump(mode="json")
    assert set(quote) == {
        "command_id",
        "symbol",
        "source",
        "observed_at",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
    }
