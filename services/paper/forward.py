"""Reviewed, paper-only decision bridge and immutable forward protocol evidence.

Role attestations are scoped to paper research; earlier independent source,
qualified compliance and performance acceptance is never inferred from them.
"""

from datetime import datetime, timedelta
from itertools import pairwise
from types import SimpleNamespace

from sqlalchemy import select

from apps.api.db import AuditRecord, DecisionRecord, SignalRecord, utcnow
from packages.schemas.control_operations import AssetApproval
from packages.schemas.controls import ControlCandidate, ControlScenario
from packages.schemas.signals import Signal
from services.controls.engine import compliance
from services.controls.store import active, latest, lock_controls
from services.decision_engine.policies import DecisionPolicy, calendar_restrictions
from services.decision_engine.store import intelligence_snapshot
from services.market_data.coverage import coverage_status
from services.market_data.event_store import ImportConflict, aware, digest, latest_events
from services.notifications.models import User
from services.paper import engine
from services.paper.models import PaperAccount, PaperCycle, PaperRun
from services.paper.schemas import OpenAccount, OrderRequest

ACTIVE = {"APPROVED", "RUNNING", "PAUSED"}


def protocol_hash(run):
    return digest(run.protocol)


def propose(session, body, actor, now=None):
    lock_controls(session)
    now = now or utcnow()
    account = session.get(PaperAccount, body.account_id)
    if not account or account.config.get("mode") != "forward":
        raise ValueError("A forward-mode paper account is required")
    old = session.get(PaperRun, body.run_id)
    payload = body.model_dump(mode="json") | {
        "account_config_sha256": digest(account.config),
        "proposed_by": actor,
    }
    if old:
        if old.protocol != payload:
            raise ImportConflict("Forward run ID conflict")
        return {
            "run_id": old.id,
            "protocol_sha256": protocol_hash(old),
            "status": old.state["status"],
            "duplicate": True,
        }
    if session.scalar(select(PaperRun).where(PaperRun.account_id == account.id)) is not None:
        raise ValueError("Use a fresh isolated account for each forward campaign")
    required = {body.provider, *body.feed_providers.values()}
    if not required <= set(body.data_review) or any(
        len(body.data_review[k]) != 64
        or any(c not in "0123456789abcdef" for c in body.data_review[k])
        for k in required
    ):
        raise ValueError("Every named source requires an explicit reviewed document hash")
    state = {
        "status": "PENDING_REVIEW",
        "proposed_by": actor,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_expires_at": None,
        "owner": None,
        "lease_until": None,
        "generation": 0,
        "started_at": None,
        "last_seen": None,
        "critical_violations": [],
        "final_report": None,
    }
    run = PaperRun(
        id=body.run_id, account_id=account.id, created_at=now, protocol=payload, state=state
    )
    session.add(run)
    session.add(AuditRecord(action="paper.protocol_proposed", subject=run.id, created_at=now))
    return {"run_id": run.id, "protocol_sha256": protocol_hash(run), "status": "PENDING_REVIEW"}


def review(session, run_id, body, actor, now=None):
    lock_controls(session)
    now = now or utcnow()
    run = session.get(PaperRun, run_id)
    reviewer = session.get(User, actor)
    if not run or run.state["status"] not in {"PENDING_REVIEW", *ACTIVE}:
        raise ValueError("Known pending or active protocol required")
    if (
        not reviewer
        or not reviewer.enabled
        or reviewer.role != "reviewer"
        or actor == run.state["proposed_by"]
    ):
        raise ValueError("A distinct enabled reviewer is required")
    if body.protocol_sha256 != protocol_hash(run):
        raise ImportConflict("Review must bind the exact protocol hash")
    if not now < body.expires_at <= now + timedelta(days=90):
        raise ValueError("Review must expire within 90 days")
    history = run.state.get("review_history", [])
    entry = {
        "actor": actor,
        "approved": body.approved,
        "expires_at": body.expires_at.isoformat(),
        "note": body.note,
        "protocol_sha256": body.protocol_sha256,
    }
    if history and all(history[-1].get(k) == v for k, v in entry.items()):
        return {
            "run_id": run.id,
            "status": run.state["status"],
            "duplicate": True,
            "authorized": False,
        }
    if len(history) >= 100:
        raise ValueError("Review history limit reached; use a new campaign")
    previously_approved = run.state.get("ever_approved", False)
    run.state = run.state | {
        "status": ("APPROVED" if body.approved else "PAUSED")
        if previously_approved
        else ("APPROVED" if body.approved else "REJECTED"),
        "review_approved": body.approved,
        "ever_approved": previously_approved or body.approved,
        "review_history": history + [entry | {"at": now.isoformat()}],
        "reviewed_by": actor,
        "reviewed_at": now.isoformat(),
        "review_expires_at": body.expires_at.isoformat(),
        "review_note": body.note,
        "reviewed_protocol_sha256": body.protocol_sha256,
    }
    session.add(AuditRecord(action="paper.protocol_reviewed", subject=run.id, created_at=now))
    return {
        "run_id": run.id,
        "status": run.state["status"],
        "protocol_sha256": protocol_hash(run),
        "authorized": False,
    }


def approved_run(session, account, now, *, current_entry_review=True):
    run = session.scalar(select(PaperRun).where(PaperRun.account_id == account.id))
    if not run or run.state["status"] not in ACTIVE:
        raise ValueError("Reviewed active forward protocol required")
    if run.state.get("reviewed_protocol_sha256") != protocol_hash(run):
        raise ValueError("Reviewed forward protocol changed")
    if not run.state.get("ever_approved"):
        raise ValueError("Paper protocol was never approved")
    if current_entry_review:
        user = session.get(User, run.state["reviewed_by"])
        proposer = session.get(User, run.state["proposed_by"])
        if not proposer or not proposer.enabled or proposer.role != "operator":
            raise ValueError("Forward proposer is unavailable")
        if (
            not user
            or not user.enabled
            or user.role != "reviewer"
            or not run.state.get("review_approved")
            or not run.state.get("review_expires_at")
            or now >= aware(datetime.fromisoformat(run.state["review_expires_at"]))
        ):
            raise ValueError("Forward reviewer or review is unavailable/expired")
    if now < aware(run.created_at) or now < aware(datetime.fromisoformat(run.state["reviewed_at"])):
        raise ValueError("Forward review is from the future")
    if run.protocol["account_config_sha256"] != digest(account.config):
        raise ValueError("Reviewed account configuration changed")
    return run


def protocol_settings(protocol):
    providers = protocol["feed_providers"]
    return SimpleNamespace(
        news_provider=providers["news"],
        calendar_provider=providers["calendar"],
        fomc_provider=providers["fomc"],
        earnings_provider=providers["earnings"],
    )


def corporate_events(session, account, now):
    return [
        row
        for row in latest_events(session, "corporate_actions", now)
        if row.payload["symbol"] in account.config["universe"]
        and aware(datetime.fromisoformat(row.payload["effective_at"])) >= aware(account.created_at)
    ]


def owned_before_action(session, account, event):
    positions = {}
    effective = aware(datetime.fromisoformat(event.payload["effective_at"]))
    for row in engine.entries(session, account.id):
        if aware(row.created_at) > effective:
            break
        for symbol, value in row.payload.get("delta", {}).get("positions", {}).items():
            if value is None:
                positions.pop(symbol, None)
            else:
                positions[symbol] = value
    return positions.get(event.payload["symbol"], {}).get("quantity", 0) > 0


def entry_guard(session, account, request, now):
    try:
        run = approved_run(session, account, now)
    except ValueError:
        return ["FORWARD_PROTOCOL_UNAVAILABLE"]
    protocol = run.protocol
    if not run.state.get("data_available"):
        return ["FORWARD_MARKET_DATA_UNAVAILABLE"]
    quote = engine.current_quote(session, account.id, request["symbol"])
    if (
        not quote
        or not quote.payload.get("session_open")
        or not aware(datetime.fromisoformat(quote.payload["session_open"]))
        <= now
        < aware(datetime.fromisoformat(quote.payload["session_close"]))
    ):
        return ["MARKET_SESSION_CLOSED"]
    decision = (
        session.get(DecisionRecord, request.get("decision_id"))
        if request.get("decision_id")
        else None
    )
    if (
        decision is None
        or not now - timedelta(seconds=protocol["decision_max_age_seconds"])
        <= aware(decision.created_at)
        <= now
    ):
        return ["FRESH_STORED_DECISION_REQUIRED"]
    signal_record = session.get(SignalRecord, decision.signal_id)
    if not signal_record or aware(signal_record.received_at) > now:
        return ["STORED_SIGNAL_REQUIRED"]
    signal = Signal.model_validate(signal_record.payload)
    expected_class = account.config.get("asset_classes", {}).get(signal.symbol, "stock")
    if (
        signal.symbol != request["symbol"]
        or signal.action != "ENTRY_CANDIDATE"
        or signal.asset_class.value != expected_class
        or not now - timedelta(minutes=15) <= signal.bar_time <= now
    ):
        return ["DECISION_SIGNAL_SCOPE_OR_FRESHNESS"]
    score = decision.response.get("snapshot", {}).get("score", 0)
    if type(score) not in (float, int) or not DecisionPolicy().minimum_score <= score <= 1:
        return ["PAPER_SCORE_BELOW_THRESHOLD"]
    policy = latest(session, "policy", account.id, now)
    asset = latest(session, "asset", signal.symbol, now)
    if not active(policy, now) or digest(policy.payload.get("policy")) != digest(
        account.config["policy"]
    ):
        return ["CURRENT_REVIEWED_PAPER_POLICY_REQUIRED"]
    if not active(asset, now):
        return ["CURRENT_ASSET_REVIEW_REQUIRED"]
    try:
        reviewed = AssetApproval.model_validate(
            {
                k: v
                for k, v in asset.payload.items()
                if k not in ("computed_financial_screen", "methodology_record_id")
            }
        )
        method = latest(session, "methodology", reviewed.assessment.methodology, now)
        if (
            not active(method, now)
            or method.payload.get("status") != "APPROVED"
            or asset.payload.get("methodology_record_id") != method.record_id
        ):
            return ["METHODOLOGY_REVIEW_CHANGED_OR_EXPIRED"]
        if reviewed.sector != account.config["universe"][signal.symbol]:
            return ["PAPER_SECTOR_REVIEW_MISMATCH"]
        config = OpenAccount.model_validate(account.config)
        profile = ControlScenario(
            as_of=now,
            candidate=ControlCandidate(
                symbol=signal.symbol,
                asset_class=expected_class,
                sector=reviewed.sector,
                action="BUY",
                quantity=request["quantity"],
                stop_price=request["stop_price"],
            ),
            policy=config.policy,
            assessment=reviewed.assessment,
            instrument=reviewed.instrument,
        )
        reasons = compliance(profile)
        if reasons:
            return reasons
    except (ValueError, KeyError):
        return ["INVALID_PAPER_REVIEW"]
    # Paper-only source assumptions are explicitly reviewed; do not change the
    # earlier research feed's provider_independently_verified or authorization flags.
    intelligence = intelligence_snapshot(
        session, signal, now, protocol_settings(protocol), DecisionPolicy()
    )
    if intelligence["event_restrictions"] or intelligence["assessment_restrictions"]:
        return ["PAPER_EVENT_OR_ASSESSMENT_RESTRICTION"]
    if any(b["code"] != "PROVIDER_UNVERIFIED" for b in intelligence["feed_blockers"]):
        return ["PAPER_INTELLIGENCE_COVERAGE_UNAVAILABLE"]
    if any(
        not f["required_feed_available"] or f["provider"] not in protocol["data_review"]
        for f in intelligence["feeds"].values()
    ):
        return ["PAPER_SOURCE_SCOPE_NOT_REVIEWED"]
    coverage = coverage_status(
        session,
        protocol["feed_providers"]["corporate_actions"],
        signal.symbol,
        expected_class,
        "corporate_actions",
        now,
        now - timedelta(days=1),
        now + timedelta(days=3),
    )
    if not coverage["required_feed_available"]:
        return ["CORPORATE_ACTION_COVERAGE_REQUIRED"]
    if any(
        e.payload["symbol"] == signal.symbol
        and now - timedelta(days=1)
        <= aware(datetime.fromisoformat(e.payload["effective_at"]))
        <= now + timedelta(days=3)
        for e in corporate_events(session, account, now)
    ):
        return ["CORPORATE_ACTION_EXCLUSION_WINDOW"]
    deadlines = [
        aware(datetime.fromisoformat(run.state["review_expires_at"])),
        aware(decision.created_at) + timedelta(seconds=protocol["decision_max_age_seconds"]),
        signal.bar_time + timedelta(minutes=15),
        reviewed.assessment.evidence.expires_at,
        reviewed.instrument.evidence.expires_at,
    ]
    deadlines.extend(
        aware(row.expires_at) for row in (policy, asset, method) if row.expires_at is not None
    )
    for feed in intelligence["feeds"].values():
        if feed.get("last_successful_at"):
            deadlines.append(
                aware(datetime.fromisoformat(feed["last_successful_at"]))
                + timedelta(minutes=DecisionPolicy().feed_age_minutes)
            )
    if coverage.get("last_successful_at"):
        deadlines.append(
            aware(datetime.fromisoformat(coverage["last_successful_at"])) + timedelta(minutes=15)
        )
    session.info["paper_entry_deadline"] = min(deadlines)
    calendar = intelligence.get("calendar_snapshot", [])
    session.info["paper_entry_events"] = lambda at: bool(
        calendar_restrictions(calendar, signal.symbol, signal.asset_class, at, DecisionPolicy())
    )
    return []


def decision_order(session, account_id, body, actor, now=None, *, already_locked=False):
    if not already_locked:
        lock_controls(session)
    injected_now = now is not None
    now = now or utcnow()
    account = session.get(PaperAccount, account_id)
    if not account or account.config.get("mode") != "forward":
        raise ValueError("Forward account required for decision bridge")
    run = approved_run(session, account, now, current_entry_review=False)
    row = session.get(DecisionRecord, body.decision_id)
    if (
        not row
        or not now - timedelta(seconds=run.protocol["decision_max_age_seconds"])
        <= aware(row.created_at)
        <= now
    ):
        raise ValueError("Fresh stored decision required")
    signal_row = session.get(SignalRecord, row.signal_id)
    if not signal_row:
        raise ValueError("Stored decision signal is missing")
    signal = Signal.model_validate(signal_row.payload)
    if (
        signal.symbol not in account.config["universe"]
        or not now - timedelta(minutes=15) <= signal.bar_time <= now
    ):
        raise ValueError("Current decision signal must match paper universe")
    side = "BUY" if signal.action == "ENTRY_CANDIDATE" else "SELL"
    if side == "BUY":
        approved_run(session, account, now)
    request = OrderRequest(
        command_id="signal:" + digest({"id": row.signal_id}),
        symbol=signal.symbol,
        side=side,
        quantity=body.quantity,
        stop_price=body.stop_price.normalize()
        if side == "BUY" and body.stop_price is not None
        else None,
        decision_id=row.id,
    )
    return engine.mutate(
        session,
        account.id,
        "order",
        request,
        "decision-bridge",
        now if injected_now else None,
        authority=engine.WORKER_AUTHORITY,
        already_locked=True,
    )


def cycles(session, run_id):
    return session.scalars(
        select(PaperCycle).where(PaperCycle.run_id == run_id).order_by(PaperCycle.sequence)
    ).all()


def cycle_seal(run_id, cycle_id, started, completed, previous, payload):
    return digest(
        {
            "run": run_id,
            "id": cycle_id,
            "started": aware(started).isoformat(),
            "completed": aware(completed).isoformat(),
            "previous": previous,
            "payload": payload,
        }
    )


def report(session, run, now=None):
    now = now or utcnow()
    if run.state["status"] == "COMPLETED" and run.state.get("final_report"):
        if digest(run.state["final_report"]) != run.state.get("final_report_sha256"):
            return {
                "status": "NOT_CONFIRMED",
                "critical_violations": ["FINAL_REPORT_HASH_MISMATCH"],
                "authorized": False,
            }
        return dict(run.state["final_report"])
    rows = cycles(session, run.id)
    chain, errors, days = engine.ZERO_HASH, [], {}
    exit_orders, workers = set(), set()
    recovery_verified = False
    protocol = run.protocol
    for row in rows:
        if row.previous_sha256 != chain or row.entry_sha256 != cycle_seal(
            run.id, row.id, row.started_at, row.completed_at, chain, row.payload
        ):
            errors.append("CYCLE_CHAIN_MISMATCH")
        chain = row.entry_sha256
        p = row.payload
        if p.get("status") == "CRITICAL":
            errors.append(p.get("error", "CRITICAL_OPERATIONAL_VIOLATION"))
        if aware(row.started_at) > aware(row.completed_at) or aware(row.completed_at) > now:
            errors.append("INVALID_CYCLE_RECEIPT_TIME")
        if p.get("status") in {"OK", "CLOSED"}:
            if p.get("worker_id"):
                workers.add(p["worker_id"])
            recovery_verified = recovery_verified or bool(p.get("recovery", {}).get("verified"))
        exit_orders.update(
            result.get("order_id")
            for result in p.get("results", [])
            if result.get("status") == "FILLED" and result.get("fill", {}).get("side") == "SELL"
        )
        if p.get("status") == "OK" and p.get("market_open") and p.get("session"):
            s = p["session"]
            day = days.setdefault(
                s["date"],
                {
                    "open": aware(datetime.fromisoformat(s["opens"])),
                    "close": aware(datetime.fromisoformat(s["closes"])),
                    "times": [],
                },
            )
            if day["open"] != aware(datetime.fromisoformat(s["opens"])) or day["close"] != aware(
                datetime.fromisoformat(s["closes"])
            ):
                errors.append("CALENDAR_CHANGED_WITHIN_SESSION")
            day["times"].append(aware(row.completed_at))
    qualifying = []
    for name, day in days.items():
        times = sorted(day["times"])
        gap = timedelta(seconds=protocol["maximum_gap_seconds"])
        if (
            now >= day["close"]
            and times[0] <= day["open"] + gap
            and times[-1] >= day["close"] - gap
            and all(b - a <= gap for a, b in pairwise(times))
        ):
            qualifying.append(name)
    account = session.get(PaperAccount, run.account_id)
    reconciliation = engine.reconcile(session, account) if account else {"status": "MISMATCH"}
    if reconciliation["status"] != "MATCH":
        errors.append("RECONCILIATION_MISMATCH")
    started = (
        aware(datetime.fromisoformat(run.state["started_at"]))
        if run.state.get("started_at")
        else None
    )
    ledger_exits = (
        {
            o.id
            for o in engine.orders(session, account.id)
            if o.request["side"] == "SELL"
            and o.state["status"] == "FILLED"
            and started
            and aware(o.created_at) >= started
        }
        if account
        else set()
    )
    if exit_orders - ledger_exits:
        errors.append("EXIT_RESULT_NOT_IN_LEDGER")
    round_trips = len(exit_orders & ledger_exits)
    restart_observed = len(workers) >= 2
    elapsed = (now - started).total_seconds() if started else 0
    blockers = []
    if not run.state.get("last_seen") or now - aware(
        datetime.fromisoformat(run.state["last_seen"])
    ) > timedelta(seconds=protocol["maximum_gap_seconds"]):
        blockers.append("WORKER_STALE")
    if len(qualifying) < protocol["minimum_sessions"]:
        blockers.append("INSUFFICIENT_COMPLETE_MARKET_SESSIONS")
    if elapsed < 20 * 86400:
        blockers.append("INSUFFICIENT_ACTUAL_ELAPSED_TIME")
    if round_trips < protocol["minimum_round_trips"]:
        blockers.append("INSUFFICIENT_COMPLETED_EXIT_ORDERS")
    if not restart_observed:
        blockers.append("WORKER_RESTART_NOT_OBSERVED")
    if not recovery_verified:
        blockers.append("ORDER_OR_POSITION_RESTART_RECOVERY_NOT_OBSERVED")
    if (
        not account
        or account.state["positions"]
        or any(o.state["status"] in engine.OPEN for o in engine.orders(session, account.id))
        or account.state["unsettled"]
    ):
        blockers.append("FINAL_FLAT_SETTLED_ACCOUNT_REQUIRED")
    try:
        if account is None:
            raise ValueError("Missing paper account")
        approved_run(session, account, now)
    except ValueError:
        if run.state["status"] != "COMPLETED":
            blockers.append("REVIEW_NOT_CURRENT")
    if run.state["status"] in {"FAILED", "REJECTED", "STOPPED"}:
        blockers.append("RUN_NOT_ELIGIBLE")
    if run.state.get("critical_violations"):
        errors.extend(run.state["critical_violations"])
    return {
        "run_id": run.id,
        "mode": "internal_forward",
        "status": "ACCEPTABLE" if not errors and not blockers else "NOT_CONFIRMED",
        "state": run.state["status"],
        "protocol_sha256": protocol_hash(run),
        "observed_seconds": max(0, elapsed),
        "qualifying_sessions": sorted(qualifying),
        "required_sessions": protocol["minimum_sessions"],
        "completed_exit_orders": round_trips,
        "required_exit_orders": protocol["minimum_round_trips"],
        "cycles": len(rows),
        "worker_state": "UNKNOWN"
        if not run.state.get("last_seen")
        else "RECENT"
        if now - aware(datetime.fromisoformat(run.state["last_seen"]))
        <= timedelta(seconds=protocol["maximum_gap_seconds"])
        else "STALE",
        "last_cycle_status": run.state.get("last_status"),
        "restart_observed": restart_observed,
        "order_or_position_recovery_verified": recovery_verified,
        "reconciliation": reconciliation["status"],
        "blockers": sorted(set(blockers)),
        "critical_violations": sorted(set(errors)),
        "authorized": False,
        "scope": "Server-recorded forward observations only; no profitability, independent source, qualified human or live-trading approval.",
    }
