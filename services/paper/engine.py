"""Transactional internal synthetic broker. No HTTP, broker credentials or live authority."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from sqlalchemy import select

from apps.api.db import AuditRecord, utcnow
from packages.schemas.controls import (
    AccountSnapshot,
    ControlCandidate,
    ControlEvidence,
    ControlScenario,
    MarketQuote,
    Position,
    Reservation,
)
from services.controls.engine import risk
from services.controls.store import latest, lock_controls
from services.market_data.event_store import ImportConflict, aware, digest
from services.paper.models import PaperAccount, PaperJournal, PaperOrder, PaperQuote
from services.paper.schemas import OpenAccount

D = Decimal
OPEN = {"ACCEPTED", "PARTIALLY_FILLED"}
ZERO_HASH = "0" * 64


def key(account_id, command_id):
    return digest({"account": account_id, "command": command_id})


def orders(session, account_id):
    return session.scalars(
        select(PaperOrder)
        .where(PaperOrder.account_id == account_id)
        .order_by(PaperOrder.created_at, PaperOrder.id)
    ).all()


def quotes(session, account_id):
    return session.scalars(
        select(PaperQuote)
        .where(PaperQuote.account_id == account_id)
        .order_by(PaperQuote.created_at, PaperQuote.id)
    ).all()


def entries(session, account_id):
    return session.scalars(
        select(PaperJournal)
        .where(PaperJournal.account_id == account_id)
        .order_by(PaperJournal.sequence)
    ).all()


def blank():
    return {
        "cash": "0",
        "unsettled": {},
        "positions": {},
        "fees": "0",
        "realized": "0",
        "halted": False,
        "halt_reason": "",
        "day": None,
        "day_start_equity": "0",
        "peak_equity": "0",
        "consecutive_losses": 0,
        "last_loss_at": None,
    }


def equity(state):
    return (
        D(state["cash"])
        + sum((D(x["amount"]) for x in state["unsettled"].values()), D(0))
        + sum((D(p["mark"]) * p["quantity"] for p in state["positions"].values()), D(0))
    )


def apply(state, delta):
    state = deepcopy(state)
    for name in ("cash", "fees", "realized"):
        state[name] = str(D(state[name]) + D(delta.get(name, "0")))
    for name in ("positions", "unsettled"):
        for item, value in delta.get(name, {}).items():
            if value is None:
                state[name].pop(item, None)
            else:
                state[name][item] = deepcopy(value)
    state.update(delta.get("meta", {}))
    return state


def seal(account_id, event_id, created, request_sha, previous, payload, result):
    return digest(
        {
            "account": account_id,
            "id": event_id,
            "at": aware(created).isoformat(),
            "request": request_sha,
            "previous": previous,
            "payload": payload,
            "result": result,
        }
    )


def reconcile(session, account):
    with localcontext() as context:
        context.prec = 80
        try:
            return _reconcile(session, account)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return {
                "status": "MISMATCH",
                "errors": ["INVALID_PAPER_RECORD"],
                "authorized": False,
                "mode": "synthetic",
            }


def _reconcile(session, account):
    """Replay durable journal, verify its chain, order projections and quote consumption."""
    expected, expected_orders, used, chain, errors = blank(), {}, {}, ZERO_HASH, []
    expected_quotes = {}
    journal = entries(session, account.id)
    for event in journal:
        if event.previous_sha256 != chain or event.entry_sha256 != seal(
            account.id,
            event.id,
            event.created_at,
            event.request_sha256,
            chain,
            event.payload,
            event.result,
        ):
            errors.append("JOURNAL_CHAIN_MISMATCH")
        chain = event.entry_sha256
        expected = apply(expected, event.payload["delta"])
        expected_orders.update(event.payload.get("orders", {}))
        if event.payload.get("quote"):
            expected_quotes[event.result["quote_id"]] = event.payload["quote"]
        fill = event.payload.get("fill")
        if fill:
            field = "ask" if fill["side"] == "BUY" else "bid"
            k = (fill["quote_id"], field)
            used[k] = used.get(k, 0) + fill["quantity"]
            amount = D(fill["price"]) * fill["quantity"]
            expected_cash = -(amount + D(fill["fee"])) if field == "ask" else D(0)
            if D(event.payload["delta"].get("cash", "0")) != expected_cash:
                errors.append("FILL_CASH_MISMATCH")
    if not journal:
        errors.append("JOURNAL_MISSING")
    elif journal[0].result.get("config_sha256") != digest(account.config):
        errors.append("CONFIG_PROJECTION_MISMATCH")
    if expected_quotes != {q.id: q.payload for q in quotes(session, account.id)}:
        errors.append("QUOTE_PROJECTION_MISMATCH")
    if expected != account.state:
        errors.append("ACCOUNT_PROJECTION_MISMATCH")
    actual_orders = {
        o.id: {"request": o.request, "state": o.state} for o in orders(session, account.id)
    }
    if expected_orders != actual_orders:
        errors.append("ORDER_PROJECTION_MISMATCH")
    for q in quotes(session, account.id):
        if q.used_ask != used.get((q.id, "ask"), 0) or q.used_bid != used.get((q.id, "bid"), 0):
            errors.append("QUOTE_CONSUMPTION_MISMATCH")
        if (
            not 0 <= q.used_ask <= q.payload["ask_size"]
            or not 0 <= q.used_bid <= q.payload["bid_size"]
        ):
            errors.append("QUOTE_LIQUIDITY_BREACH")
    if {q for q, _ in used} - {q.id for q in quotes(session, account.id)}:
        errors.append("FILL_QUOTE_MISSING")
    if D(expected["cash"]) < 0 or any(
        p["quantity"] < 0 or D(p["cost"]) < 0 for p in expected["positions"].values()
    ):
        errors.append("NEGATIVE_BALANCE")
    holds = sum(
        (
            D(o.state["reserved_cash"])
            for o in orders(session, account.id)
            if o.state["status"] in OPEN
        ),
        D(0),
    )
    if holds > D(expected["cash"]):
        errors.append("CASH_RESERVATION_BREACH")
    for symbol in {o.request["symbol"] for o in orders(session, account.id)}:
        shares = sum(
            o.state["reserved_shares"]
            for o in orders(session, account.id)
            if o.request["symbol"] == symbol and o.state["status"] in OPEN
        )
        if shares > expected["positions"].get(symbol, {}).get("quantity", 0):
            errors.append("SHARE_RESERVATION_BREACH")
    return {
        "status": "MATCH" if not errors else "MISMATCH",
        "errors": sorted(set(errors)),
        "journal_entries": len(journal),
        "last_sequence": journal[-1].sequence if journal else None,
        "authorized": False,
        "mode": "synthetic",
    }


def record(
    session,
    account,
    command_id,
    request_sha,
    actor,
    now,
    kind,
    delta,
    result,
    changed=(),
    fill=None,
    quote=None,
):
    config = OpenAccount.model_validate(account.config)
    state = apply(account.state, delta)
    day = now.astimezone(ZoneInfo(config.policy.loss_day_timezone)).date().isoformat()
    meta = delta.setdefault("meta", {})
    if account.state["day"] != day:
        meta.update(
            day=day,
            day_start_equity=str(
                equity(account.state) if account.state["day"] else config.initial_cash
            ),
        )
    meta["peak_equity"] = str(max(D(account.state["peak_equity"]), equity(state)))
    account.state = apply(account.state, delta)
    prior = session.scalar(
        select(PaperJournal)
        .where(PaperJournal.account_id == account.id)
        .order_by(PaperJournal.sequence.desc())
        .limit(1)
    )
    previous = prior.entry_sha256 if prior else ZERO_HASH
    event_id = key(account.id, command_id)
    payload = {
        "kind": kind,
        "actor": actor,
        "delta": delta,
        "orders": {o.id: {"request": o.request, "state": o.state} for o in changed},
    }
    if fill:
        payload["fill"] = fill
    if quote:
        payload["quote"] = quote
    result = {"mode": "synthetic", "authorized": False, **result}
    event = PaperJournal(
        id=event_id,
        account_id=account.id,
        created_at=now,
        request_sha256=request_sha,
        previous_sha256=previous,
        entry_sha256=seal(account.id, event_id, now, request_sha, previous, payload, result),
        payload=payload,
        result=result,
    )
    session.add(event)
    session.add(AuditRecord(action="paper." + kind.lower(), subject=account.id, created_at=now))
    session.flush()
    return result


def open_account(session, request, actor, now=None):
    lock_controls(session)
    now = now or utcnow()
    checksum = digest({"kind": "open", "actor": actor, "request": request.model_dump(mode="json")})
    old = session.get(PaperAccount, request.account_id)
    if old:
        event = session.scalar(
            select(PaperJournal).where(PaperJournal.id == key(old.id, "__open__"))
        )
        if not event or event.request_sha256 != checksum:
            raise ImportConflict("Paper account ID conflict")
        return event.result | {"duplicate": True}
    account = PaperAccount(
        id=request.account_id, created_at=now, config=request.model_dump(mode="json"), state=blank()
    )
    session.add(account)
    return record(
        session,
        account,
        "__open__",
        checksum,
        actor,
        now,
        "OPEN",
        {"cash": str(request.initial_cash)},
        {"status": "OPEN", "account_id": account.id, "config_sha256": digest(account.config)},
    )


def current_quote(session, account_id, symbol):
    rows = [q for q in quotes(session, account_id) if q.payload["symbol"] == symbol]
    return max(
        rows,
        key=lambda q: (aware(datetime.fromisoformat(q.payload["observed_at"])), q.id),
        default=None,
    )


def fresh(q, now, seconds):
    return (
        q is not None
        and aware(q.created_at) <= now
        and now - timedelta(seconds=seconds)
        <= aware(datetime.fromisoformat(q.payload["observed_at"]))
        <= now
    )


def evidence(now):
    return ControlEvidence(
        evidence_id="synthetic-paper",
        provider="internal-simulator",
        document_sha256=ZERO_HASH,
        observed_at=now,
        recorded_at=now,
        effective_at=now,
        expires_at=now + timedelta(seconds=1),
    )


def entry_check(session, account, request, quantity, cap, now, exclude=None):
    config, state = OpenAccount.model_validate(account.config), account.state
    existing = state["positions"].get(request["symbol"])
    stops = [
        D(o.request["stop_price"])
        for o in orders(session, account.id)
        if o.id != exclude
        and o.state["status"] in OPEN
        and o.request["side"] == "BUY"
        and o.request["symbol"] == request["symbol"]
    ]
    if existing:
        stops.append(D(existing["stop"]))
    if any(stop != D(request["stop_price"]) for stop in stops):
        return ["POSITION_STOP_MISMATCH"]
    kill = latest(session, "kill", account.id, now)
    policy = config.policy.model_copy(
        update={
            "kill_switch": state["halted"]
            or config.policy.kill_switch
            or bool(kill and kill.payload["engaged"])
        }
    )
    if equity(state) <= 0:
        return ["NONPOSITIVE_EQUITY"]
    for symbol in {request["symbol"], *state["positions"]}:
        if not fresh(current_quote(session, account.id, symbol), now, policy.quote_max_age_seconds):
            return ["QUOTE_UNAVAILABLE_OR_STALE"]
    positions = [
        Position(
            symbol=symbol,
            asset_class="stock",
            sector=p["sector"],
            quantity=p["quantity"],
            sellable_quantity=p["quantity"],
            market_value=D(p["mark"]) * p["quantity"],
            open_risk=max(D(0), D(p["mark"]) - D(p["stop"]) * (1 - policy.slippage_bps / D(10000)))
            * p["quantity"]
            + policy.fee_per_share * p["quantity"]
            + policy.fee_per_order,
        )
        for symbol, p in state["positions"].items()
    ]
    reservations = [
        Reservation(
            reservation_id=o.id,
            symbol=o.request["symbol"],
            sector=config.universe[o.request["symbol"]],
            side=o.request["side"],
            quantity=o.request["quantity"] - o.state["filled"],
            notional=D(o.state["reserved_cash"]) - D(o.state["reserved_fee"]),
            estimated_fee=D(o.state["reserved_fee"]),
            planned_risk=D(o.state["planned_risk"]),
        )
        for o in orders(session, account.id)
        if o.id != exclude and o.state["status"] in OPEN
    ]
    day = now.astimezone(ZoneInfo(policy.loss_day_timezone)).date()
    realized_today = sum(
        (
            D(e.payload["delta"].get("realized", "0"))
            for e in entries(session, account.id)
            if aware(e.created_at).astimezone(ZoneInfo(policy.loss_day_timezone)).date() == day
        ),
        D(0),
    )
    snapshot = AccountSnapshot(
        account_id=account.id,
        evidence=evidence(now),
        connected=True,
        account_type="cash",
        lending_enabled=False,
        borrowing_enabled=False,
        positions_complete=True,
        reservations_complete=True,
        equity=equity(state),
        day_start_equity=D(state["day_start_equity"])
        if state["day"] == day.isoformat()
        else equity(state),
        peak_equity=max(equity(state), D(state["peak_equity"])),
        settled_cash=D(state["cash"]),
        trading_day=day,
        realized_pnl_today=realized_today,
        consecutive_losses=state["consecutive_losses"],
        last_loss_at=state["last_loss_at"],
        positions=positions,
        reservations=reservations,
    )
    ask = cap / (1 + policy.slippage_bps / D(10000))
    scenario = ControlScenario(
        as_of=now,
        candidate=ControlCandidate(
            symbol=request["symbol"],
            asset_class="stock",
            sector=config.universe[request["symbol"]],
            action="BUY",
            quantity=quantity,
            stop_price=request["stop_price"],
        ),
        policy=policy,
        account=snapshot,
        quote=MarketQuote(
            symbol=request["symbol"],
            asset_class="stock",
            evidence=evidence(now),
            bid=ask,
            ask=ask,
            required_feeds_fresh=True,
        ),
    )
    return risk(scenario)["reasons"]


def terminal(order, status):
    order.state = order.state | {
        "status": status,
        "reserved_cash": "0",
        "reserved_fee": "0",
        "reserved_shares": 0,
        "planned_risk": "0",
    }


def close_loss(state, order, now):
    """Count one realized outcome per completed/cancelled exit order, not per fill."""
    if order.request["side"] != "SELL" or not order.state["filled"] or order.state["loss_counted"]:
        return {}
    losing = D(order.state["realized"]) < 0
    order.state = order.state | {"loss_counted": True}
    meta = {"consecutive_losses": state["consecutive_losses"] + 1 if losing else 0}
    if losing:
        meta["last_loss_at"] = now.isoformat()
    return meta


def submit(session, account, body, actor, now, checksum):
    config = OpenAccount.model_validate(account.config)
    request = body.model_dump(mode="json")
    order_id = key(account.id, body.command_id)
    rejected = []
    q = current_quote(session, account.id, body.symbol)
    if body.symbol not in config.universe:
        rejected.append("SYMBOL_OUTSIDE_SYNTHETIC_UNIVERSE")
    if not fresh(q, now, config.policy.quote_max_age_seconds):
        rejected.append("QUOTE_UNAVAILABLE_OR_STALE")
    cap = body.limit_price or (
        D(q.payload["ask"]) * (1 + config.policy.slippage_bps / D(10000)) if q else D(0)
    )
    fee = config.policy.fee_per_share * body.quantity + config.policy.fee_per_order
    if not rejected and body.side == "BUY":
        rejected.extend(entry_check(session, account, request, body.quantity, cap, now))
    if body.side == "SELL":
        held = account.state["positions"].get(body.symbol, {}).get("quantity", 0)
        reserved = sum(
            o.state["reserved_shares"]
            for o in orders(session, account.id)
            if o.request["symbol"] == body.symbol and o.state["status"] in OPEN
        )
        if body.quantity > held - reserved:
            rejected.append("INSUFFICIENT_OWNED_SHARES")
    state = {
        "status": "REJECTED" if rejected else "ACCEPTED",
        "filled": 0,
        "average_price": "0",
        "fees": "0",
        "realized": "0",
        "loss_counted": False,
        "cap": str(cap),
        "reserved_cash": str(cap * body.quantity + fee)
        if body.side == "BUY" and not rejected
        else "0",
        "reserved_fee": str(fee) if body.side == "BUY" and not rejected else "0",
        "reserved_shares": body.quantity if body.side == "SELL" and not rejected else 0,
        "planned_risk": str(
            max(D(0), cap - D(body.stop_price or 0) * (1 - config.policy.slippage_bps / D(10000)))
            * body.quantity
            + 2 * fee
        )
        if body.side == "BUY" and not rejected
        else "0",
        "reasons": rejected,
        "expires_at": (now + timedelta(seconds=body.expires_in_seconds)).isoformat(),
    }
    order = PaperOrder(
        id=order_id, account_id=account.id, created_at=now, request=request, state=state
    )
    session.add(order)
    return record(
        session,
        account,
        body.command_id,
        checksum,
        actor,
        now,
        "ORDER",
        {},
        {"order_id": order_id, **state},
        [order],
    )


def ingest_quote(session, account, body, actor, now, checksum):
    config = OpenAccount.model_validate(account.config)
    if body.symbol not in config.universe:
        raise ValueError("Quote symbol outside synthetic universe")
    if not now - timedelta(seconds=config.policy.quote_max_age_seconds) <= body.observed_at <= now:
        raise ValueError("Quote is stale or in the future")
    old = current_quote(session, account.id, body.symbol)
    if old and body.observed_at <= aware(datetime.fromisoformat(old.payload["observed_at"])):
        raise ValueError("Quote observations must increase")
    quote_id = key(account.id, body.command_id)
    body = body.model_copy(update={"observed_at": body.observed_at.astimezone(UTC)})
    session.add(
        PaperQuote(
            id=quote_id,
            account_id=account.id,
            created_at=now,
            payload=body.model_dump(mode="json"),
            used_bid=0,
            used_ask=0,
        )
    )
    positions = {}
    if body.symbol in account.state["positions"]:
        positions[body.symbol] = account.state["positions"][body.symbol] | {"mark": str(body.bid)}
    return record(
        session,
        account,
        body.command_id,
        checksum,
        actor,
        now,
        "QUOTE",
        {"positions": positions},
        {"status": "RECORDED", "quote_id": quote_id},
        quote=body.model_dump(mode="json"),
    )


def find_order(session, account, order_id):
    order = session.get(PaperOrder, order_id)
    if not order or order.account_id != account.id:
        raise ValueError("Unknown order in this paper account")
    return order


def fill_order(session, account, body, actor, now, checksum):
    config, state = OpenAccount.model_validate(account.config), account.state
    order = find_order(session, account, body.order_id)
    if order.state["status"] not in OPEN:
        return record(
            session,
            account,
            body.command_id,
            checksum,
            actor,
            now,
            "NO_FILL",
            {},
            {"status": "NO_FILL", "reason": "ORDER_TERMINAL"},
        )
    if now >= aware(datetime.fromisoformat(order.state["expires_at"])):
        terminal(order, "EXPIRED")
        return record(
            session,
            account,
            body.command_id,
            checksum,
            actor,
            now,
            "EXPIRE",
            {"meta": close_loss(state, order, now)},
            {"status": "EXPIRED", "order_id": order.id},
            [order],
        )
    q = session.get(PaperQuote, body.quote_id)
    if (
        not q
        or q.account_id != account.id
        or q.payload["symbol"] != order.request["symbol"]
        or not fresh(q, now, config.policy.quote_max_age_seconds)
    ):
        raise ValueError("Matching fresh quote required")
    if aware(datetime.fromisoformat(q.payload["observed_at"])) < aware(order.created_at) or aware(
        q.created_at
    ) < aware(order.created_at):
        raise ValueError("Fills require a quote observed and received after order submission")
    if current_quote(session, account.id, order.request["symbol"]).id != q.id:
        raise ValueError("Latest quote required")
    buy = order.request["side"] == "BUY"
    price = D(q.payload["ask" if buy else "bid"]) * (
        1 + (1 if buy else -1) * config.policy.slippage_bps / D(10000)
    )
    limit = order.request["limit_price"]
    # A limit is an execution bound, never invent a better-than-quote fill.
    if (buy and price > D(order.state["cap"])) or (limit and not buy and price < D(limit)):
        return record(
            session,
            account,
            body.command_id,
            checksum,
            actor,
            now,
            "NO_FILL",
            {},
            {"status": "NO_FILL", "reason": "PRICE_OUTSIDE_BOUND"},
        )
    remaining = order.request["quantity"] - order.state["filled"]
    if buy:
        blockers = entry_check(
            session, account, order.request, remaining, D(order.state["cap"]), now, order.id
        )
        if blockers:
            terminal(order, "CANCELLED")
            order.state = order.state | {"reasons": blockers}
            return record(
                session,
                account,
                body.command_id,
                checksum,
                actor,
                now,
                "RISK_CANCEL",
                {},
                {"status": "CANCELLED", "reasons": blockers, "order_id": order.id},
                [order],
            )
    available = (
        (q.payload["ask_size"] - q.used_ask) if buy else (q.payload["bid_size"] - q.used_bid)
    )
    quantity = min(remaining, available)
    if quantity <= 0:
        return record(
            session,
            account,
            body.command_id,
            checksum,
            actor,
            now,
            "NO_FILL",
            {},
            {"status": "NO_FILL", "reason": "QUOTE_LIQUIDITY_EXHAUSTED"},
        )
    fee = config.policy.fee_per_share * quantity + (
        config.policy.fee_per_order if order.state["filled"] == 0 else D(0)
    )
    symbol = order.request["symbol"]
    old = state["positions"].get(symbol)
    delta = {"fees": str(fee), "positions": {}}
    realized = D(0)
    fill_id = key(account.id, body.command_id)
    if buy:
        amount = price * quantity + fee
        if amount > D(state["cash"]):
            raise ValueError("Insufficient settled synthetic cash")
        p = old or {
            "quantity": 0,
            "cost": "0",
            "sector": config.universe[symbol],
            "mark": q.payload["bid"],
            "stop": order.request["stop_price"],
        }
        p = p | {
            "quantity": p["quantity"] + quantity,
            "cost": str(D(p["cost"]) + amount),
            "mark": q.payload["bid"],
            "stop": str(min(D(p["stop"]), D(order.request["stop_price"]))),
        }
        delta.update(cash=str(-amount))
        q.used_ask += quantity
    else:
        if not old or old["quantity"] < quantity:
            raise ValueError("Insufficient owned synthetic shares")
        proceeds = price * quantity - fee
        if proceeds < 0:
            raise ValueError("Fees exceed synthetic sale proceeds")
        cost = D(old["cost"]) * quantity / old["quantity"]
        realized = proceeds - cost
        p = old | {
            "quantity": old["quantity"] - quantity,
            "cost": str(D(old["cost"]) - cost),
            "mark": q.payload["bid"],
        }
        if not p["quantity"]:
            p = None
        delta.update(
            unsettled={
                fill_id: {
                    "amount": str(proceeds),
                    "available_at": (
                        now + timedelta(seconds=config.settlement_delay_seconds)
                    ).isoformat(),
                }
            },
            realized=str(realized),
        )
        q.used_bid += quantity
    delta["positions"][symbol] = p
    filled = order.state["filled"] + quantity
    average = (D(order.state["average_price"]) * order.state["filled"] + price * quantity) / filled
    remaining = order.request["quantity"] - filled
    remaining_fee = config.policy.fee_per_share * remaining
    order.state = order.state | {
        "status": "FILLED" if remaining == 0 else "PARTIALLY_FILLED",
        "filled": filled,
        "average_price": str(average),
        "fees": str(D(order.state["fees"]) + fee),
        "realized": str(D(order.state["realized"]) + realized),
        "reserved_cash": str(D(order.state["cap"]) * remaining + remaining_fee) if buy else "0",
        "reserved_fee": str(remaining_fee) if buy else "0",
        "reserved_shares": remaining if not buy else 0,
        "planned_risk": str(
            max(
                D(0),
                D(order.state["cap"])
                - D(order.request["stop_price"] or 0) * (1 - config.policy.slippage_bps / D(10000)),
            )
            * remaining
            + 2 * remaining_fee
            + (2 * config.policy.fee_per_order if remaining else D(0))
        )
        if buy
        else "0",
    }
    if remaining == 0:
        delta["meta"] = close_loss(state, order, now)
    fill = {
        "order_id": order.id,
        "quote_id": q.id,
        "side": order.request["side"],
        "symbol": symbol,
        "quantity": quantity,
        "price": str(price),
        "fee": str(fee),
        "realized": str(realized),
    }
    return record(
        session,
        account,
        body.command_id,
        checksum,
        actor,
        now,
        "FILL",
        delta,
        {"status": order.state["status"], "order_id": order.id, "fill": fill},
        [order],
        fill,
    )


def cancel_order(session, account, body, actor, now, checksum):
    order = find_order(session, account, body.order_id)
    if order.state["status"] in OPEN:
        terminal(order, "CANCELLED")
    meta = close_loss(account.state, order, now)
    return record(
        session,
        account,
        body.command_id,
        checksum,
        actor,
        now,
        "CANCEL",
        {"meta": meta},
        {"status": order.state["status"], "order_id": order.id},
        [order],
    )


def tick(session, account, body, actor, now, checksum):
    due = {
        k: v
        for k, v in account.state["unsettled"].items()
        if aware(datetime.fromisoformat(v["available_at"])) <= now
    }
    changed = []
    meta = {}
    for order in orders(session, account.id):
        if (
            order.state["status"] in OPEN
            and aware(datetime.fromisoformat(order.state["expires_at"])) <= now
        ):
            terminal(order, "EXPIRED")
            meta.update(close_loss(account.state | meta, order, now))
            changed.append(order)
    return record(
        session,
        account,
        body.command_id,
        checksum,
        actor,
        now,
        "TICK",
        {
            "cash": str(sum((D(v["amount"]) for v in due.values()), D(0))),
            "unsettled": {k: None for k in due},
            "meta": meta,
        },
        {"status": "APPLIED", "settlements": len(due), "expired_orders": len(changed)},
        changed,
    )


def halt(session, account, body, actor, now, checksum):
    changed = []
    if body.engaged:
        for order in orders(session, account.id):
            if order.state["status"] in OPEN and order.request["side"] == "BUY":
                terminal(order, "CANCELLED")
                changed.append(order)
    return record(
        session,
        account,
        body.command_id,
        checksum,
        actor,
        now,
        "HALT",
        {"meta": {"halted": body.engaged, "halt_reason": body.reason}},
        {"status": "HALTED" if body.engaged else "RESUMED"},
        changed,
    )


OPERATIONS = {
    "order": submit,
    "quote": ingest_quote,
    "fill": fill_order,
    "cancel": cancel_order,
    "tick": tick,
    "halt": halt,
}


def mutate(session, account_id, kind, body, actor, now=None):
    lock_controls(session)
    now = now or utcnow()  # Sample after lock waits; time injection is for isolated tests only.
    account = session.get(PaperAccount, account_id)
    if account is None:
        raise ValueError("Unknown paper account")
    checksum = digest({"kind": kind, "request": body.model_dump(mode="json"), "actor": actor})
    if body.command_id == "__open__":
        raise ImportConflict("Reserved paper command ID")
    prior = session.scalar(
        select(PaperJournal).where(PaperJournal.id == key(account_id, body.command_id))
    )
    if prior:
        if prior.request_sha256 != checksum:
            raise ImportConflict("Paper command ID conflict")
        return prior.result | {"duplicate": True}
    last = session.scalar(
        select(PaperJournal)
        .where(PaperJournal.account_id == account.id)
        .order_by(PaperJournal.sequence.desc())
        .limit(1)
    )
    if last and now < aware(last.created_at):
        raise ValueError("Paper server clock moved backwards")
    with localcontext() as context:
        context.prec = 80
        check = reconcile(session, account)
        if check["status"] != "MATCH":
            # Never repair or overwrite drift automatically.
            session.add(
                AuditRecord(
                    action="paper.reconciliation_blocked", subject=account.id, created_at=now
                )
            )
            return {
                "status": "BLOCKED",
                "reason": "RECONCILIATION_MISMATCH",
                "errors": check["errors"],
                "authorized": False,
                "mode": "synthetic",
            }
        return OPERATIONS[kind](session, account, body, actor, now, checksum)


def snapshot(session, account):
    with localcontext() as context:
        context.prec = 80
        rows = orders(session, account.id)
        held = sum((D(o.state["reserved_cash"]) for o in rows if o.state["status"] in OPEN), D(0))
        return {
            "account_id": account.id,
            "mode": "synthetic",
            "authorized": False,
            "config": account.config,
            "state": account.state,
            "equity": str(equity(account.state)),
            "reserved_cash": str(held),
            "available_cash": str(D(account.state["cash"]) - held),
            "orders": [{"id": o.id, "request": o.request, "state": o.state} for o in rows],
            "reconciliation": reconcile(session, account),
            "forward_acceptance": "NOT_ESTABLISHED",
        }
