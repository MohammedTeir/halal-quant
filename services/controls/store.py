"""Append-only role attestations and serialized, server-derived research controls.

Human/provider truth is not cryptographically verified. No record grants execution.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from apps.api.db import (
    AuditRecord,
    BrokerCapture,
    ControlCheckRecord,
    ControlLock,
    ControlReservation,
    ControlRevision,
    SignalRecord,
    utcnow,
)
from packages.schemas.control_operations import (
    AssetApproval,
    MethodologyApproval,
    RiskReconciliation,
)
from packages.schemas.controls import (
    AccountSnapshot,
    ControlCandidate,
    ControlEvidence,
    ControlPolicy,
    ControlScenario,
    MarketQuote,
    Position,
    Reservation,
)
from packages.schemas.signals import Signal
from services.controls.engine import KINDS, compliance, evidence_current, preview
from services.market_data.event_store import ImportConflict, aware, digest


def lock_controls(session):
    query = select(ControlLock).where(ControlLock.id == "controls-v1")
    if session.bind.dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    else:
        query = query.with_for_update()
    if session.scalar(query) is None:
        raise ValueError("Controls lock migration missing")


def latest(session, kind, scope, as_of):
    # Latest known effective revision wins, including an expired/rejected tombstone.
    return session.scalar(
        select(ControlRevision)
        .where(
            ControlRevision.kind == kind,
            ControlRevision.scope == scope,
            ControlRevision.received_at <= as_of,
            ControlRevision.effective_at <= as_of,
        )
        .order_by(ControlRevision.sequence.desc())
        .limit(1)
    )


def active(record, as_of):
    return record is not None and (record.expires_at is None or as_of < aware(record.expires_at))


def stamp(evidence, now):
    if evidence.observed_at > now or evidence.recorded_at > now:
        raise ValueError("Future evidence is unavailable")
    return evidence.model_copy(
        update={
            "recorded_at": now,
            "observed_at": evidence.observed_at.astimezone(UTC),
            "effective_at": evidence.effective_at.astimezone(UTC),
            "expires_at": evidence.expires_at.astimezone(UTC),
        }
    )


def put_revision(
    session, kind, scope, record_id, payload, actor, now, effective, expires, request_sha
):
    prior = session.scalar(select(ControlRevision).where(ControlRevision.record_id == record_id))
    if prior:
        if prior.request_sha256 != request_sha or prior.actor != actor:
            raise ImportConflict("Control record ID conflict")
        return {
            "record_id": record_id,
            "duplicate": True,
            "authorized": False,
            "sequence": prior.sequence,
        }
    record = ControlRevision(
        record_id=record_id,
        kind=kind,
        scope=scope,
        request_sha256=request_sha,
        actor=actor,
        received_at=now,
        effective_at=effective.astimezone(UTC),
        expires_at=expires.astimezone(UTC) if expires else None,
        payload=payload,
    )
    session.add(record)
    session.add(AuditRecord(action="controls_" + kind, subject=record_id, created_at=now))
    session.flush()
    return {
        "record_id": record_id,
        "duplicate": False,
        "authorized": False,
        "sequence": record.sequence,
    }


def ratios(financials, method):
    with localcontext() as context:
        context.prec = 80
        values = {
            "debt": financials.debt / financials.denominator_value,
            "interest_assets": financials.interest_assets / financials.denominator_value,
            "impure_income": financials.impure_revenue / financials.total_revenue,
        }
        limits = {
            "debt": method.maximum_debt_ratio,
            "interest_assets": method.maximum_interest_assets_ratio,
            "impure_income": method.maximum_impure_income_ratio,
        }
        missing = []
        if method.maximum_receivables_cash_ratio is not None:
            limits["receivables_cash"] = method.maximum_receivables_cash_ratio
            if financials.receivables_cash is None:
                missing.append("receivables_cash")
            else:
                values["receivables_cash"] = (
                    financials.receivables_cash / financials.denominator_value
                )
        matches = financials.denominator == method.denominator
        checks = {}
        for key, limit in limits.items():
            boundary = (
                method.impure_income_boundary
                if key == "impure_income" and method.impure_income_boundary
                else method.ratio_boundary
            )
            checks[key] = key in values and (
                values[key] < limit if boundary == "strictly_below" else values[key] <= limit
            )
        result = {
            "eligible_for_reviewer_consideration": matches and all(checks.values()),
            "denominator_matches": matches,
            "ratios": {k: str(v) for k, v in values.items()},
            "checks": checks,
            "automatic_shariah_approval": False,
        }
        if missing:
            result["missing_required_inputs"] = missing
        return result


def review(session, kind, request, actor, now):
    lock_controls(session)
    now = utcnow()  # Capacity and receipt time are sampled after lock waits.
    checksum = digest({"kind": kind, "request": request.model_dump(mode="json"), "actor": actor})
    old = session.scalar(
        select(ControlRevision).where(ControlRevision.record_id == request.record_id)
    )
    if old:
        if old.request_sha256 != checksum:
            raise ImportConflict("Control record ID conflict")
        return {
            "record_id": old.record_id,
            "sequence": old.sequence,
            "duplicate": True,
            "authorized": False,
        }
    payload = request.model_dump(mode="json")
    if kind == "asset":
        a = request.assessment.model_copy(
            update={"evidence": stamp(request.assessment.evidence, now)}
        )
        instrument = request.instrument.model_copy(
            update={"evidence": stamp(request.instrument.evidence, now)}
        )
        scope = a.symbol
        effective = max(a.evidence.effective_at, instrument.evidence.effective_at)
        expires = min(a.evidence.expires_at, instrument.evidence.expires_at)
        if effective >= expires:
            raise ValueError("Asset/instrument validity windows do not overlap")
        payload.update(
            assessment=a.model_dump(mode="json"), instrument=instrument.model_dump(mode="json")
        )
        if a.status == "APPROVED":
            validation_at = max(now, effective)
            method_record = latest(session, "methodology", a.methodology, validation_at)
            if (
                not active(method_record, validation_at)
                or method_record.payload.get("status") != "APPROVED"
            ):
                raise ValueError("Current qualified methodology attestation required")
            method = MethodologyApproval.model_validate(method_record.payload)
            if a.asset_class == "stock":
                if request.financials is None:
                    raise ValueError("Stock financial inputs required")
                computed = ratios(request.financials, method)
                if not computed["eligible_for_reviewer_consideration"]:
                    raise ValueError("Stock ratios fail selected methodology")
                payload["computed_financial_screen"] = computed
            candidate = ControlCandidate(
                symbol=a.symbol, asset_class=a.asset_class, sector=request.sector, action="BUY"
            )
            scenario = ControlScenario(
                as_of=validation_at,
                candidate=candidate,
                policy=ControlPolicy(methodology=a.methodology),
                assessment=a,
                instrument=instrument,
            )
            if compliance(scenario):
                raise ValueError(
                    "APPROVED review has missing/failed asset or instrument conditions"
                )
        payload["methodology_record_id"] = (
            method_record.record_id if a.status == "APPROVED" else None
        )
    else:
        evidence = stamp(request.evidence, now)
        payload["evidence"] = evidence.model_dump(mode="json")
        effective, expires = evidence.effective_at, evidence.expires_at
        scope = request.methodology_id if kind == "methodology" else request.account_id
    response = put_revision(
        session, kind, scope, request.record_id, payload, actor, now, effective, expires, checksum
    )
    if kind == "asset" and request.assessment.status != "APPROVED":
        captures = session.scalars(
            select(BrokerCapture)
            .where(
                BrokerCapture.kind == "account",
                BrokerCapture.status == "SUCCEEDED",
                BrokerCapture.completed_at <= now,
            )
            .order_by(BrokerCapture.sequence.desc())
        ).all()
        seen = set()
        for capture in captures:
            if capture.scope in seen:
                continue
            seen.add(capture.scope)
            if any(
                p["symbol"] == scope and Decimal(p["quantity"]) > 0
                for p in capture.payload["positions"]
            ):
                method_record = latest(session, "methodology", request.assessment.methodology, now)
                guidance = (
                    method_record.payload["divestment_guidance"]
                    if active(method_record, now)
                    else "Qualified reviewer disposition required; no automatic hold or liquidation ruling"
                )
                review_id = "divest:" + digest(
                    {"asset": request.record_id, "account": capture.scope}
                )
                disposition = {
                    "symbol": scope,
                    "account_id": capture.scope,
                    "asset_record_id": request.record_id,
                    "status": "REVIEW_REQUIRED",
                    "last_observed_broker_capture": capture.id,
                    "guidance": guidance,
                    "automatic_liquidation": False,
                    "human_truth_automatically_verified": False,
                }
                put_revision(
                    session,
                    "divestment",
                    capture.scope,
                    review_id,
                    disposition,
                    actor,
                    now,
                    effective,
                    None,
                    digest(disposition),
                )
    return response


def kill_switch(session, request, engaged, actor, now):
    lock_controls(session)
    now = utcnow()  # Capacity and receipt time are sampled after lock waits.
    payload = request.model_dump(mode="json") | {"engaged": engaged}
    result = put_revision(
        session,
        "kill",
        request.account_id,
        request.record_id,
        payload,
        actor,
        now,
        now,
        None,
        digest({"request": request.model_dump(mode="json"), "engaged": engaged, "actor": actor}),
    )

    if engaged and not result["duplicate"]:
        from services.notifications.delivery import enqueue

        enqueue(session, "risk_stop", "kill:" + request.record_id, {"status": "ENGAGED"})
    return result


def capture_latest(session, kind, scope, as_of):
    return session.scalar(
        select(BrokerCapture)
        .where(
            BrokerCapture.kind == kind,
            BrokerCapture.scope == scope,
            BrokerCapture.created_at <= as_of,
        )
        .order_by(BrokerCapture.sequence.desc())
        .limit(1)
    )


def capture_view(record):
    # Do not disclose cash, account number, raw positions or provider response text here.
    return {
        "refresh_id": record.id,
        "kind": record.kind,
        "status": record.status,
        "error_code": record.error_code,
        "completed_at": aware(record.completed_at).isoformat() if record.completed_at else None,
        "scope": record.scope,
        "authorized": False,
    }


def current_capture(session, kind, scope, now, max_age):
    record = capture_latest(session, kind, scope, now)
    if kind == "account":
        newest = session.scalar(
            select(BrokerCapture)
            .where(BrokerCapture.kind == "account", BrokerCapture.created_at <= now)
            .order_by(BrokerCapture.sequence.desc())
            .limit(1)
        )
        if newest is None or newest.scope != scope:
            return None
        record = newest
    if (
        record is None
        or record.status != "SUCCEEDED"
        or not record.completed_at
        or not record.payload
    ):
        return None
    observed = datetime.fromisoformat(record.payload["observed_at"])
    if not observed <= aware(record.completed_at) <= now or now - observed > timedelta(
        seconds=max_age
    ):
        return None
    return record


def operational_context(session, account_id, signal, now, settings, request=None):
    """Server-owned facts only. Signal/desired stop/quantity remain technical proposals."""
    blockers = []
    refs = {}
    policy_record = latest(session, "policy", account_id, now)
    policy = ControlPolicy()
    if not active(policy_record, now):
        blockers.append("CURRENT_REVIEWED_POLICY_MISSING")
    else:
        policy = ControlPolicy.model_validate(policy_record.payload["policy"])
        refs["policy"] = policy_record.record_id
    asset_record = latest(session, "asset", signal.symbol, now)
    assessment = instrument = None
    sector = "UNKNOWN"
    if not active(asset_record, now):
        blockers.append("CURRENT_ASSET_REVIEW_MISSING")
    else:
        asset = AssetApproval.model_validate(
            {
                k: v
                for k, v in asset_record.payload.items()
                if k not in ("computed_financial_screen", "methodology_record_id")
            }
        )
        assessment, instrument, sector = asset.assessment, asset.instrument, asset.sector
        refs["asset"] = asset_record.record_id
        method_record = latest(session, "methodology", assessment.methodology, now)
        if assessment.status != "APPROVED":
            blockers.append("ASSET_" + assessment.status)
        elif (
            not active(method_record, now)
            or method_record.payload.get("status") != "APPROVED"
            or asset_record.payload.get("methodology_record_id") != method_record.record_id
        ):
            blockers.append("METHODOLOGY_REVIEW_CHANGED_OR_UNAVAILABLE")
        else:
            refs["methodology"] = method_record.record_id
    kill = latest(session, "kill", account_id, now)
    if kill:
        policy = policy.model_copy(update={"kill_switch": bool(kill.payload["engaged"])})
    if kill:
        refs["kill_switch"] = kill.record_id
    account_capture = current_capture(
        session, "account", account_id, now, policy.broker_max_age_seconds
    )
    if account_capture is None:
        blockers.append("CURRENT_BROKER_CAPTURE_MISSING")
    else:
        refs["broker_capture"] = account_capture.id
    candidate = ControlCandidate(
        symbol=signal.symbol, asset_class=signal.asset_class.value, sector=sector, action="BUY"
    )
    profile = ControlScenario(
        as_of=now, candidate=candidate, policy=policy, assessment=assessment, instrument=instrument
    )
    compliance_pass = not compliance(profile) and not any(
        b in blockers
        for b in ("CURRENT_ASSET_REVIEW_MISSING", "METHODOLOGY_REVIEW_CHANGED_OR_UNAVAILABLE")
    )
    instrument_pass = bool(
        instrument
        and (instrument.symbol, instrument.asset_class) == (signal.symbol, signal.asset_class.value)
        and evidence_current(instrument.evidence, now)
        and instrument.kind == KINDS[signal.asset_class.value]
        and instrument.settlement_and_possession_pass is True
    )
    return {
        "compliance_pass": compliance_pass,
        "instrument_pass": instrument_pass,
        "blockers": blockers,
        "references": refs,
        "policy": policy,
        "assessment": assessment,
        "instrument": instrument,
        "sector": sector,
        "account_capture": account_capture,
    }


def active_reservations(session, account_id, as_of, exclude_id=None):
    records = session.scalars(
        select(ControlReservation).where(
            ControlReservation.account_id == account_id,
            ControlReservation.created_at <= as_of,
            ControlReservation.expires_at > as_of,
        )
    ).all()
    return [
        r for r in records if r.id != exclude_id and latest(session, "release", r.id, as_of) is None
    ]


def _check(session, request, now, settings, exclude_reservation=None):
    signal_record = session.get(SignalRecord, request.signal_id)
    if signal_record is None or aware(signal_record.received_at) > now:
        raise ValueError("Known signal required")
    signal = Signal.model_validate(signal_record.payload)
    if signal.bar_time > now or now - signal.bar_time > timedelta(minutes=15):
        raise ValueError("Current closed signal required")
    ctx = operational_context(session, request.account_id, signal, now, settings)
    refs = ctx["references"]
    policy = ctx["policy"]
    account_capture = ctx["account_capture"]
    side = "BUY" if signal.action == "ENTRY_CANDIDATE" else "SELL"
    blockers = list(ctx["blockers"])
    owned = side == "SELL"
    result = None
    if owned:
        # Entry policy/compliance/kill switches cannot prevent a freshly observed owned exit.
        blockers = [b for b in blockers if b == "CURRENT_BROKER_CAPTURE_MISSING"]
        facts = account_capture.payload if account_capture else None
        qty = request.quantity
        if qty is None or qty != qty.to_integral_value():
            blockers.append("WHOLE_EXIT_QUANTITY_REQUIRED")
        available = Decimal(0)
        if facts:
            if not facts["positions_complete"] or not facts["orders_complete"]:
                blockers.append("BROKER_POSITION_OR_ORDER_CAPTURE_INCOMPLETE")
            p = next((p for p in facts["positions"] if p["symbol"] == signal.symbol), None)
            if p is None or signal.asset_class.value not in ("stock", "etf"):
                blockers.append("OWNERSHIP_UNVERIFIED")
            else:
                held = sum(
                    (
                        Decimal(r.payload["quantity"])
                        for r in active_reservations(
                            session, request.account_id, now, exclude_reservation
                        )
                        if r.payload["side"] == "SELL" and r.payload["symbol"] == signal.symbol
                    ),
                    Decimal(0),
                )
                broker_sells = sum(
                    (
                        Decimal(o["quantity"])
                        for o in facts["orders"]
                        if o["side"] == "SELL" and o["symbol"] == signal.symbol
                    ),
                    Decimal(0),
                )
                available = max(
                    Decimal(0),
                    min(Decimal(p["available_quantity"]), Decimal(p["quantity"]) - broker_sells)
                    - held,
                )
                if qty is not None and qty > available:
                    blockers.append("INSUFFICIENT_SELLABLE_QUANTITY")
        result = {
            "passed": not blockers,
            "quantity": str(qty) if not blockers else "0",
            "available_sellable_quantity": str(available),
            "reasons": blockers,
            "compliance_divestment_review_required": not ctx["compliance_pass"],
            "owned_exit_requires_execution_revalidation": True,
        }
    else:
        risk_record = latest(session, "risk", request.account_id, now)
        reconciliation = (
            RiskReconciliation.model_validate(risk_record.payload)
            if active(risk_record, now)
            else None
        )
        if reconciliation is None:
            blockers.append("CURRENT_RISK_RECONCILIATION_MISSING")
        else:
            refs["risk_reconciliation"] = risk_record.record_id
        quote_capture = current_capture(
            session, "quote", signal.symbol, now, policy.quote_max_age_seconds
        )
        if quote_capture is None:
            blockers.append("CURRENT_SERVER_QUOTE_MISSING")
        else:
            refs["quote_capture"] = quote_capture.id
        if signal.asset_class.value == "gold":
            blockers.append("BROKER_DOES_NOT_ATTEST_ALLOCATED_GOLD")
        facts = account_capture.payload if account_capture else None
        if facts:
            if (
                facts.get("activity_trading_day")
                != now.astimezone(ZoneInfo(policy.loss_day_timezone)).date().isoformat()
            ):
                blockers.append("BROKER_ACTIVITY_DAY_MISMATCH")
            if not facts.get("cash_account_verified") or not facts.get("settled_cash_verified"):
                blockers.append("CASH_ACCOUNT_OR_SETTLED_CASH_UNVERIFIED")
            if not facts.get("lending_disabled_verified") or not facts.get(
                "borrowing_disabled_verified"
            ):
                blockers.append("LENDING_OR_BORROWING_CONTRACT_UNVERIFIED")
            if facts.get("unsupported_positions_present"):
                blockers.append("UNSUPPORTED_EXISTING_POSITIONS")
            if reconciliation and (
                not reconciliation.history_complete
                or not facts["activity_complete"]
                or reconciliation.broker_activity_sha256 != facts["activity_sha256"]
            ):
                blockers.append("RISK_HISTORY_UNRECONCILED")
        if not blockers:
            account, more = _build_account(
                session, request.account_id, facts, reconciliation, policy, now, exclude_reservation
            )
            blockers.extend(more)
            if not more:
                q = quote_capture.payload
                evidence = _capture_evidence(quote_capture, now, policy.quote_max_age_seconds)
                quote = MarketQuote(
                    symbol=signal.symbol,
                    asset_class=signal.asset_class.value,
                    evidence=evidence,
                    bid=q["bid"],
                    ask=q["ask"],
                    required_feeds_fresh=True,
                )
                scenario = ControlScenario(
                    as_of=now,
                    candidate=ControlCandidate(
                        symbol=signal.symbol,
                        asset_class=signal.asset_class.value,
                        sector=ctx["sector"],
                        action="BUY",
                        stop_price=request.stop_price,
                        quantity=request.quantity,
                    ),
                    policy=policy,
                    assessment=ctx["assessment"],
                    instrument=ctx["instrument"],
                    account=account,
                    quote=quote,
                )
                result = preview(scenario)
                if result["status"] != "SIMULATION_PASS":
                    blockers.extend(
                        code for x in result["checks"].values() for code in x["reasons"]
                    )
    passed = not blockers
    quantity = (
        str(request.quantity)
        if owned and passed
        else str(result["checks"]["risk"]["quantity"])
        if passed
        else "0"
    )
    return {
        "research_controls_pass": passed,
        "blockers": blockers,
        "quantity": quantity,
        "side": side,
        "symbol": signal.symbol,
        "asset_class": signal.asset_class.value,
        "sector": ctx["sector"],
        "references": refs,
        "detail": result,
        "as_of": now.isoformat(),
        "authorized": False,
        "state_source": "server_stored_reviewer_attestations_and_broker_observations",
        "human_or_scholarly_truth_automatically_verified": False,
    }, ctx


def _capture_evidence(capture, now, age):
    return ControlEvidence(
        evidence_id=capture.id,
        provider=capture.payload["provider"],
        document_sha256=capture.payload["raw_response_sha256"],
        observed_at=datetime.fromisoformat(capture.payload["observed_at"]),
        recorded_at=aware(capture.completed_at),
        effective_at=aware(capture.completed_at),
        expires_at=aware(capture.completed_at) + timedelta(seconds=age),
    )


def _build_account(
    session, account_id, facts, reconciliation, policy, now, exclude_reservation=None
):
    blockers = []
    positions = []
    reservations = []
    orders = facts["orders"]
    sell_totals = {}
    for order in orders:
        if order.get("asset_class") != "us_equity":
            blockers.append("UNSUPPORTED_OR_UNKNOWN_BROKER_ORDER")
        if order["side"] == "SELL":
            sell_totals[order["symbol"]] = sell_totals.get(order["symbol"], Decimal(0)) + Decimal(
                order["quantity"]
            )
    for ticker, quantity in sell_totals.items():
        owned = next(
            (Decimal(p["quantity"]) for p in facts["positions"] if p["symbol"] == ticker),
            Decimal(0),
        )
        if quantity > owned:
            blockers.append("UNOWNED_OR_OVERSUBSCRIBED_SELL_ORDER")
    for p in facts["positions"]:
        if Decimal(p["quantity"]) != Decimal(p["quantity"]).to_integral_value():
            blockers.append("FRACTIONAL_EXISTING_CUSTODY_UNVERIFIED")
        review_record = latest(session, "asset", p["symbol"], now)
        if not active(review_record, now):
            blockers.append("POSITION_CLASSIFICATION_UNVERIFIED")
            continue
        a = review_record.payload["assessment"]
        sector = review_record.payload["sector"]
        # A fully covering broker-observed protective stop is necessary for known open risk.
        stops = []
        for order in orders:
            if order["symbol"] == p["symbol"] and order["side"] == "SELL":
                candidates = [order, *order.get("legs", [])]
                stops.extend(
                    o
                    for o in candidates
                    if o["type"] == "stop"
                    and o["side"] == "SELL"
                    and o["asset_class"] == "us_equity"
                    and o["symbol"] == p["symbol"]
                    and o["status"] in ("new", "accepted", "partially_filled")
                    and o["stop_price"]
                    and Decimal(o["quantity"]) >= Decimal(p["quantity"])
                )
        risk_value = None
        if stops:
            worst = min(Decimal(o["stop_price"]) for o in stops)
            risk_value = (
                max(
                    Decimal(0),
                    Decimal(p["market_value"])
                    - Decimal(p["quantity"]) * worst * (1 - policy.slippage_bps / 10000),
                )
                + 2 * policy.fee_per_order
                + 2 * policy.fee_per_share * Decimal(p["quantity"])
            )
        positions.append(
            Position(
                symbol=p["symbol"],
                asset_class=a["asset_class"],
                sector=sector,
                quantity=p["quantity"],
                sellable_quantity=p["available_quantity"],
                market_value=p["market_value"],
                open_risk=risk_value,
            )
        )
    for order in orders:
        if order["side"] != "BUY":
            continue
        if order["type"] != "limit" or not order["limit_price"]:
            blockers.append("PENDING_BUY_PRICE_UNBOUNDED")
            continue
        review_record = latest(session, "asset", order["symbol"], now)
        if not active(review_record, now):
            blockers.append("RESERVATION_CLASSIFICATION_UNVERIFIED")
            continue
        quantity = Decimal(order["quantity"])
        price = Decimal(order["limit_price"]) * (1 + policy.slippage_bps / 10000)
        stop = next(
            (
                o
                for o in order.get("legs", [])
                if o["side"] == "SELL"
                and o["type"] == "stop"
                and o["stop_price"]
                and o["asset_class"] == "us_equity"
                and o["symbol"] == order["symbol"]
                and o["status"] in ("new", "accepted", "partially_filled")
                and Decimal(o["quantity"]) >= quantity
            ),
            None,
        )
        if stop is not None and Decimal(stop["stop_price"]) >= price:
            blockers.append("PENDING_BUY_STOP_INVALID")
        risk_value = (
            None
            if stop is None
            else max(
                Decimal(0), price - Decimal(stop["stop_price"]) * (1 - policy.slippage_bps / 10000)
            )
            * quantity
            + 2 * policy.fee_per_order
            + 2 * policy.fee_per_share * quantity
        )
        if quantity > 0:
            reservations.append(
                Reservation(
                    reservation_id="broker:" + order["id"],
                    symbol=order["symbol"],
                    sector=review_record.payload["sector"],
                    side="BUY",
                    quantity=quantity,
                    notional=quantity * price,
                    estimated_fee=policy.fee_per_order + policy.fee_per_share * quantity,
                    planned_risk=risk_value,
                )
            )
    for r in active_reservations(session, account_id, now, exclude_reservation):
        if r.payload["side"] == "BUY":
            reservations.append(
                Reservation.model_validate(
                    {k: v for k, v in r.payload.items() if k in Reservation.model_fields}
                )
            )
    if Decimal(facts["equity"]) <= 0:
        blockers.append("NONPOSITIVE_BROKER_EQUITY")
    if blockers:
        return None, blockers
    capture = current_capture(session, "account", account_id, now, policy.broker_max_age_seconds)
    snapshots = session.scalars(
        select(BrokerCapture).where(
            BrokerCapture.kind == "account",
            BrokerCapture.scope == account_id,
            BrokerCapture.status == "SUCCEEDED",
            BrokerCapture.completed_at <= now,
        )
    ).all()
    peak = max(
        [
            reconciliation.peak_equity,
            Decimal(facts["equity"]),
            *(Decimal(x.payload["equity"]) for x in snapshots),
        ]
    )
    return AccountSnapshot(
        account_id=account_id,
        evidence=_capture_evidence(capture, now, policy.broker_max_age_seconds),
        connected=facts["broker_connected"],
        account_type="cash",
        lending_enabled=False,
        borrowing_enabled=False,
        positions_complete=facts["positions_complete"],
        reservations_complete=facts["orders_complete"],
        equity=facts["equity"],
        day_start_equity=reconciliation.day_start_equity,
        peak_equity=peak,
        settled_cash=facts["settled_cash"],
        trading_day=reconciliation.trading_day,
        realized_pnl_today=reconciliation.realized_pnl_today,
        consecutive_losses=reconciliation.consecutive_losses,
        last_loss_at=reconciliation.last_loss_at,
        positions=tuple(positions),
        reservations=tuple(reservations),
    ), []


def check_and_reserve(session, request, now, settings):
    lock_controls(session)
    now = utcnow()  # Capacity and receipt time are sampled after lock waits.
    checksum = digest(request.model_dump(mode="json"))
    old = session.get(ControlCheckRecord, request.check_id)
    if old:
        if old.request_sha256 != checksum:
            raise ImportConflict("Control check ID conflict")
        held = next(
            (
                r
                for r in active_reservations(session, request.account_id, now)
                if r.id == request.check_id
            ),
            None,
        )
        return old.payload | {
            "duplicate": True,
            "reservation_active_now": held is not None,
            "recorded_result_replayed": True,
        }
    with localcontext() as context:
        context.prec = 80
        result, ctx = _check(session, request, now, settings)
    result["request"] = request.model_dump(mode="json")
    result.update(
        check_id=request.check_id,
        account_id=request.account_id,
        signal_id=request.signal_id,
        duplicate=False,
    )
    if request.reserve and result["research_controls_pass"]:
        prior = session.scalars(
            select(ControlReservation).where(
                ControlReservation.account_id == request.account_id,
                ControlReservation.signal_id == request.signal_id,
            )
        ).all()
        if any(r in active_reservations(session, request.account_id, now) for r in prior):
            result.update(
                research_controls_pass=False, blockers=["SIGNAL_ALREADY_RESERVED"], quantity="0"
            )
        else:
            duration = min(
                15, ctx["policy"].broker_max_age_seconds, ctx["policy"].quote_max_age_seconds
            )
            expires = now + timedelta(seconds=duration)
            for capture_id in [
                ctx["references"].get("broker_capture"),
                ctx["references"].get("quote_capture"),
            ]:
                if capture_id:
                    capture = get_capture(session, capture_id)
                    age = (
                        ctx["policy"].broker_max_age_seconds
                        if capture.kind == "account"
                        else ctx["policy"].quote_max_age_seconds
                    )
                    expires = min(
                        expires,
                        datetime.fromisoformat(capture.payload["observed_at"])
                        + timedelta(seconds=age),
                    )
            for kind, ref in [
                ("policy", ctx["references"].get("policy")),
                ("asset", ctx["references"].get("asset")),
                ("methodology", ctx["references"].get("methodology")),
                ("risk", ctx["references"].get("risk_reconciliation")),
            ]:
                if ref:
                    evidence_record = session.scalar(
                        select(ControlRevision).where(ControlRevision.record_id == ref)
                    )
                    if evidence_record and evidence_record.expires_at:
                        expires = min(expires, aware(evidence_record.expires_at))
            if expires <= now:
                result.update(
                    research_controls_pass=False,
                    blockers=["RESERVATION_EVIDENCE_EXPIRED"],
                    quantity="0",
                )
            else:
                d = result["detail"]["checks"]["risk"] if result["side"] == "BUY" else None
                notional = (
                    Decimal(result["quantity"]) * Decimal(d["entry_with_slippage"])
                    if d
                    else Decimal(0)
                )
                cash = Decimal(d["estimated_cash_required"]) if d else Decimal(0)
                payload = {
                    "reservation_id": request.check_id,
                    "symbol": result["symbol"],
                    "sector": result["sector"],
                    "side": result["side"],
                    "quantity": result["quantity"],
                    "notional": str(notional),
                    "estimated_fee": str(cash - notional),
                    "planned_risk": d["planned_risk"] if d else "0",
                    "simulation_only": True,
                    "not_a_broker_order": True,
                }
                session.add(
                    ControlReservation(
                        id=request.check_id,
                        account_id=request.account_id,
                        signal_id=request.signal_id,
                        created_at=now,
                        expires_at=expires,
                        payload=payload,
                    )
                )
                result["reservation"] = {
                    "reservation_id": request.check_id,
                    "expires_at": expires.isoformat(),
                    "simulation_only": True,
                }
    session.add(
        ControlCheckRecord(
            id=request.check_id,
            request_sha256=checksum,
            account_id=request.account_id,
            signal_id=request.signal_id,
            created_at=now,
            payload=result,
        )
    )
    risk_stops = sorted(
        set(result["blockers"])
        & {
            "KILL_SWITCH_ACTIVE",
            "DAILY_LOSS_LIMIT",
            "DRAWDOWN_LIMIT",
            "CONSECUTIVE_LOSS_COOLDOWN",
        }
    )
    if risk_stops:
        from services.notifications.delivery import enqueue

        enqueue(
            session, "risk_stop", "check:" + request.check_id, {"status": ", ".join(risk_stops)}
        )
    session.add(AuditRecord(action="controls_checked", subject=request.check_id, created_at=now))
    session.flush()
    return result


def release(session, request, actor, now):
    lock_controls(session)
    now = utcnow()  # Capacity and receipt time are sampled after lock waits.
    reservation = session.get(ControlReservation, request.reservation_id)
    if reservation is None:
        raise ValueError("Unknown reservation")
    return put_revision(
        session,
        "release",
        request.reservation_id,
        request.release_id,
        request.model_dump(mode="json"),
        actor,
        now,
        now,
        None,
        digest({"request": request.model_dump(mode="json"), "actor": actor}),
    )


def get_capture(session, capture_id):
    return session.scalar(select(BrokerCapture).where(BrokerCapture.id == capture_id))


def revalidate_evaluation(session, check_id, signal, as_of, settings):
    from packages.schemas.control_operations import ControlCheck

    record = session.get(ControlCheckRecord, check_id)
    if record is None or aware(record.created_at) > as_of or record.signal_id != signal.event_id:
        raise ValueError("Known matching control check required at evaluation time")
    reservation = session.get(ControlReservation, check_id)
    if reservation is None or reservation not in active_reservations(
        session, record.account_id, as_of
    ):
        return {
            "research_controls_pass": False,
            "blockers": ["CONTROL_RESERVATION_MISSING_OR_EXPIRED"],
            "authorized": False,
        }, None
    original = ControlCheck.model_validate(record.payload["request"])
    pinned = original.model_copy(update={"quantity": Decimal(reservation.payload["quantity"])})
    with localcontext() as context:
        context.prec = 80
        return _check(session, pinned, as_of, settings, exclude_reservation=check_id)
