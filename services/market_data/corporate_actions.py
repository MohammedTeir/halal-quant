"""Mathematical split consistency checks; not provider or compliance verification."""

import hashlib
import json
import math
from datetime import UTC, datetime

import numpy as np

from packages.schemas.data_events import ActionObservation
from services.market_data.csv_data import Dataset


def verify_split_adjustments(
    raw: Dataset, adjusted: Dataset, observations: list[ActionObservation], as_of: datetime
):
    if as_of.tzinfo is None or as_of < raw.bars.index[-1].to_pydatetime():
        raise ValueError("as_of must be aware and at/after the data window")
    if (raw.spec.symbol, raw.spec.asset_class, raw.spec.timeframe_seconds, raw.spec.source) != (
        adjusted.spec.symbol,
        adjusted.spec.asset_class,
        adjusted.spec.timeframe_seconds,
        adjusted.spec.source,
    ) or not raw.bars.index.equals(adjusted.bars.index):
        raise ValueError("Raw and adjusted snapshots must describe matching observations")
    if raw.spec.asset_class not in ("stock", "etf") or raw.spec.price_basis != "unadjusted":
        raise ValueError("Raw stock/ETF prices required")
    if adjusted.spec.price_basis != "split_adjusted":
        raise ValueError(
            "Only split-adjusted OHLC is supported; total-return verification is deferred"
        )
    if raw.spec.volume_basis != "as_reported":
        raise ValueError("Raw volume must be as reported")
    as_of = as_of.astimezone(UTC)
    latest = {}
    identities = {}
    for item in observations:
        action = item.action
        if item.received_at < action.published_at:
            raise ValueError("Action cannot be received before publication")
        if action.provider != raw.spec.source or action.symbol != raw.spec.symbol:
            raise ValueError("Action provenance does not match snapshot source/symbol")
        if action.published_at <= as_of and item.received_at <= as_of:
            identity = (action.item_id, action.revision)
            payload = action.model_dump(mode="json")
            if identity in identities and identities[identity] != payload:
                raise ValueError("Conflicting source revision in action ledger")
            identities[identity] = payload
        if (
            action.published_at <= as_of
            and item.received_at <= as_of
            and (
                action.item_id not in latest
                or latest[action.item_id].action.revision < action.revision
            )
        ):
            latest[action.item_id] = item
    factors = np.ones(len(raw.bars))
    applied, instants = [], set()
    for item in latest.values():
        action = item.action
        if (
            action.action_type != "split"
            or action.effective_at > raw.bars.index[-1].to_pydatetime()
        ):
            continue
        if action.effective_at in instants:
            raise ValueError("Ambiguous multiple split records at the same effective instant")
        instants.add(action.effective_at)
        ratio = float(action.split_ratio)
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError("Split ratio exceeds supported numerical precision")
        factors[raw.bars.index < action.effective_at] /= ratio
        if not np.isfinite(factors).all() or (factors <= 0).any():
            raise ValueError("Cumulative adjustment exceeds supported numerical precision")
        applied.append(
            {
                "item_id": action.item_id,
                "revision": action.revision,
                "split_ratio": str(action.split_ratio),
                "effective_at": action.effective_at.isoformat(),
            }
        )
    expected = raw.bars[["Open", "High", "Low", "Close"]].to_numpy() * factors[:, None]
    actual = adjusted.bars[["Open", "High", "Low", "Close"]].to_numpy()
    max_price_error = float(np.max(np.abs(expected - actual)))
    quantum = (
        float(adjusted.spec.adjustment_rounding_quantum)
        if adjusted.spec.adjustment_rounding_quantum
        else None
    )
    checks = np.isclose(expected, actual, rtol=1e-7, atol=1e-8)
    if quantum is not None:
        changed = factors != 1
        units = actual[changed] / quantum
        checks[changed] = np.abs(expected[changed] - actual[changed]) <= quantum / 2 + 1e-8
        if not np.allclose(units, np.round(units), rtol=0, atol=1e-6):
            checks[changed] = False
    price_consistent = bool(checks.all())
    expected_volume = raw.bars.Volume.to_numpy()
    if adjusted.spec.volume_basis == "split_adjusted":
        expected_volume = expected_volume / factors
    volume_consistent = bool(
        np.allclose(expected_volume, adjusted.bars.Volume, rtol=1e-7, atol=1e-8)
    )
    return {
        "schema_version": "1.0",
        "as_of": as_of.isoformat(),
        "action_observations_sha256": hashlib.sha256(
            json.dumps(
                [item.model_dump(mode="json") for item in observations],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "consistent": price_consistent and volume_consistent,
        "synthetic": raw.spec.synthetic
        or adjusted.spec.synthetic
        or any(item.action.synthetic for item in observations),
        "prices_consistent": price_consistent,
        "adjustment_rounding_quantum": str(adjusted.spec.adjustment_rounding_quantum)
        if quantum is not None
        else None,
        "maximum_price_error": max_price_error,
        "volume_consistent": volume_consistent,
        "volume_basis": adjusted.spec.volume_basis,
        "applied_splits": sorted(applied, key=lambda a: (a["effective_at"], a["item_id"])),
        "raw": raw.manifest(),
        "adjusted": adjusted.manifest(),
        "provider_independently_verified": False,
        "authorized_for_paper": False,
    }
