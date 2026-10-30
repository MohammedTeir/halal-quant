"""Fictional qualified-broker/reviewer inputs; never vendor compatibility evidence."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def evidence(name, now=None):
    now = now or datetime.now(UTC)
    return {
        "evidence_id": name,
        "provider": "qualified_fixture",
        "document_sha256": "a" * 64,
        "observed_at": (now - timedelta(seconds=2)).isoformat(),
        "recorded_at": (now - timedelta(seconds=1)).isoformat(),
        "effective_at": (now - timedelta(minutes=5)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
    }


def attestation():
    return {
        "note": "Fictional test reviewer attestation only",
        "references": ["https://example.invalid/fixture-proof"],
    }


def methodology(record_id="method-v1"):
    return dict(
        **attestation(),
        record_id=record_id,
        methodology_id="method-v1",
        status="APPROVED",
        evidence=evidence("method-proof"),
        denominator="total_assets",
        maximum_debt_ratio="0.30",
        maximum_interest_assets_ratio="0.30",
        maximum_impure_income_ratio="0.05",
        ratio_boundary="strictly_below",
        divestment_guidance="Qualified reviewer decides divestment; no automatic liquidation",
    )


def asset(symbol="AAPL", record_id="asset-v1", status="APPROVED"):
    return dict(
        **attestation(),
        record_id=record_id,
        sector="technology",
        assessment={
            "symbol": symbol,
            "asset_class": "stock",
            "status": status,
            "methodology": "method-v1",
            "evidence": evidence("asset-proof"),
            "purification_guidance": "Fictional guidance; actual scholar review required",
            "business_activity_pass": True,
            "financial_ratios_pass": True,
        },
        instrument={
            "symbol": symbol,
            "asset_class": "stock",
            "kind": "equity",
            "evidence": evidence("instrument-proof"),
            "settlement_and_possession_pass": True,
        },
        financials={
            "denominator": "total_assets",
            "denominator_value": "1000",
            "debt": "100",
            "interest_assets": "100",
            "total_revenue": "100",
            "impure_revenue": "1",
        },
    )


def policy(record_id="policy-v1"):
    return dict(
        **attestation(),
        record_id=record_id,
        account_id="acct-fixture",
        evidence=evidence("policy-proof"),
        policy={"version": record_id, "methodology": "method-v1"},
    )


def risk_state(record_id="risk-v1"):
    from zoneinfo import ZoneInfo

    return dict(
        **attestation(),
        record_id=record_id,
        account_id="acct-fixture",
        evidence=evidence("risk-proof"),
        trading_day=datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
        day_start_equity="10000",
        peak_equity="10000",
        realized_pnl_today="0",
        consecutive_losses=0,
        history_complete=True,
        broker_activity_sha256="b" * 64,
    )


def signal(event="signal-ops-1", action="ENTRY_CANDIDATE"):
    return {
        "schema_version": "1.0",
        "event_id": event,
        "strategy": "adaptive_pullback",
        "strategy_version": "1.0.0",
        "symbol": "AAPL",
        "asset_class": "stock",
        "timeframe": "1D",
        "action": action,
        "bar_time": (datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
        "price": "100",
    }


def broker_facts():
    return {
        "provider": "qualified_test_fixture",
        "account_id": "acct-fixture",
        "observed_at": datetime.now(UTC).isoformat(),
        "equity": "10000",
        "reported_cash": "10000",
        "settled_cash": "10000",
        "broker_connected": True,
        "positions": [],
        "orders": [],
        "positions_complete": True,
        "orders_complete": True,
        "activity_complete": True,
        "activity_trading_day": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
        "unsupported_positions_present": False,
        "activity_sha256": "b" * 64,
        "cash_account_verified": True,
        "settled_cash_verified": True,
        "lending_disabled_verified": True,
        "borrowing_disabled_verified": True,
        "raw_response_sha256": "c" * 64,
        "limitations": ["Fictional broker contract test; not Alpaca evidence"],
    }


class FakeBroker:
    def __init__(self, facts=None):
        self.facts = facts
        self.calls = []

    def account(self):
        self.calls.append("account")
        return self.facts or broker_facts()

    def quote(self, symbol):
        self.calls.append("quote")
        return {
            "provider": "qualified_test_quote",
            "symbol": symbol,
            "bid": "100",
            "ask": "100",
            "observed_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            "raw_response_sha256": "d" * 64,
        }
