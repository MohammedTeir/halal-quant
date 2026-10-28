import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from packages.schemas.data_events import ActionObservation, CorporateAction
from services.market_data.corporate_actions import verify_split_adjustments
from services.market_data.csv_data import load_csv
from services.market_data.validate_actions import main
from services.technical_signals.strategies import defaults, features

AS_OF = datetime(2020, 1, 8, tzinfo=UTC)


def snapshots(make_dataset, ratio=2, adjusted_volume=True):
    prices = [100, 102, 104, 104 / ratio, 106 / ratio, 108 / ratio]
    raw = make_dataset(prices=prices)
    raw.spec = raw.spec.model_copy(update={"price_basis": "unadjusted"})
    raw.bars["Open"] = raw.bars.Close
    raw.bars["High"] = raw.bars.Close + 0.2
    raw.bars["Low"] = raw.bars.Close - 0.2
    adjusted = replace(
        raw,
        bars=raw.bars.copy(),
        spec=raw.spec.model_copy(
            update={
                "price_basis": "split_adjusted",
                "volume_basis": "split_adjusted" if adjusted_volume else "as_reported",
            }
        ),
    )
    adjusted.bars.loc[adjusted.bars.index[:3], ["Open", "High", "Low", "Close"]] /= ratio
    if adjusted_volume:
        adjusted.bars.loc[adjusted.bars.index[:3], "Volume"] *= ratio
    action = CorporateAction(
        provider="test_fixture",
        item_id="split",
        symbol="EXAMPLE",
        action_type="split",
        split_ratio=str(ratio),
        effective_at=raw.bars.index[3].to_pydatetime(),
        published_at=datetime(2019, 12, 20, tzinfo=UTC),
    )
    observation = ActionObservation(action=action, received_at=datetime(2019, 12, 21, tzinfo=UTC))
    return raw, adjusted, observation


@pytest.mark.parametrize("ratio", [2, 0.1])
@pytest.mark.parametrize("adjusted_volume", [False, True])
def test_forward_reverse_split_and_explicit_volume_basis(make_dataset, ratio, adjusted_volume):
    raw, adjusted, observation = snapshots(make_dataset, ratio, adjusted_volume)
    report = verify_split_adjustments(raw, adjusted, [observation], AS_OF)
    assert report["consistent"] and report["prices_consistent"] and report["volume_consistent"]
    assert report["applied_splits"][0]["split_ratio"] == str(ratio)
    assert not report["authorized_for_paper"] and not report["provider_independently_verified"]
    assert len(report["action_observations_sha256"]) == 64


def test_missing_late_or_wrong_adjustment_cannot_pass(make_dataset):
    raw, adjusted, observation = snapshots(make_dataset)
    assert not verify_split_adjustments(raw, adjusted, [], AS_OF)["consistent"]
    late = observation.model_copy(update={"received_at": AS_OF + timedelta(days=1)})
    assert not verify_split_adjustments(raw, adjusted, [late], AS_OF)["consistent"]
    # An otherwise plausible gap or declaration cannot substitute for arithmetic.
    changed = replace(adjusted, bars=adjusted.bars.copy())
    changed.bars.loc[changed.bars.index[0], "Close"] += 1
    assert not verify_split_adjustments(raw, changed, [observation], AS_OF)["prices_consistent"]
    changed = replace(adjusted, bars=adjusted.bars.copy())
    changed.bars.loc[changed.bars.index[0], "Volume"] /= 2
    assert not verify_split_adjustments(raw, changed, [observation], AS_OF)["volume_consistent"]


def test_action_revision_is_known_only_after_receipt(make_dataset):
    raw, adjusted, first = snapshots(make_dataset)
    correction = ActionObservation(
        action=first.action.model_copy(
            update={
                "revision": 2,
                "split_ratio": first.action.split_ratio * 2,
                "published_at": AS_OF + timedelta(days=1),
            }
        ),
        received_at=AS_OF + timedelta(days=2),
    )
    assert verify_split_adjustments(raw, adjusted, [first, correction], AS_OF)["consistent"]
    assert not verify_split_adjustments(
        raw, adjusted, [first, correction], AS_OF + timedelta(days=3)
    )["consistent"]


def test_provenance_scope_ambiguous_ledgers_and_total_returns_rejected(make_dataset):
    raw, adjusted, item = snapshots(make_dataset)
    bad = item.model_copy(update={"action": item.action.model_copy(update={"provider": "another"})})
    with pytest.raises(ValueError, match="provenance"):
        verify_split_adjustments(raw, adjusted, [bad], AS_OF)
    duplicate = item.model_copy(
        update={"action": item.action.model_copy(update={"item_id": "duplicate"})}
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        verify_split_adjustments(raw, adjusted, [item, duplicate], AS_OF)
    conflicting = item.model_copy(
        update={
            "action": item.action.model_copy(update={"split_ratio": item.action.split_ratio * 2})
        }
    )
    with pytest.raises(ValueError, match="Conflicting"):
        verify_split_adjustments(raw, adjusted, [item, conflicting], AS_OF)
    adjusted.spec = adjusted.spec.model_copy(update={"price_basis": "total_return_adjusted"})
    with pytest.raises(ValueError, match="total-return"):
        verify_split_adjustments(raw, adjusted, [item], AS_OF)


def test_dividend_fields_and_temporal_validation(make_dataset):
    raw, adjusted, item = snapshots(make_dataset)
    with pytest.raises(ValueError):
        CorporateAction(
            provider="p",
            item_id="x",
            symbol="X",
            action_type="split",
            split_ratio="1",
            published_at=AS_OF,
            effective_at=AS_OF,
        )
    with pytest.raises(ValueError):
        CorporateAction(
            provider="p",
            item_id="x",
            symbol="X",
            action_type="cash_dividend",
            cash_amount="-1",
            published_at=AS_OF,
            effective_at=AS_OF,
        )
    with pytest.raises(ValueError, match="before publication"):
        verify_split_adjustments(
            raw,
            adjusted,
            [item.model_copy(update={"received_at": datetime(2019, 1, 1, tzinfo=UTC)})],
            AS_OF,
        )
    with pytest.raises(ValueError, match="as_of"):
        verify_split_adjustments(raw, adjusted, [item], AS_OF.replace(tzinfo=None))
    with pytest.raises(ValueError, match="as_of"):
        verify_split_adjustments(raw, adjusted, [item], raw.bars.index[2].to_pydatetime())


def test_multiple_splits_compose_without_adjusting_effective_bar(make_dataset):
    raw, adjusted, item = snapshots(make_dataset)
    second = item.model_copy(
        update={
            "action": item.action.model_copy(
                update={"item_id": "second", "effective_at": raw.bars.index[5].to_pydatetime()}
            )
        }
    )
    adjusted.bars.loc[adjusted.bars.index[:5], ["Open", "High", "Low", "Close"]] /= 2
    adjusted.bars.loc[adjusted.bars.index[:5], "Volume"] *= 2
    report = verify_split_adjustments(raw, adjusted, [item, second], AS_OF)
    assert report["consistent"] and len(report["applied_splits"]) == 2
    assert np.allclose(raw.bars.iloc[-1], adjusted.bars.iloc[-1])


def test_raw_csv_can_be_audited_but_never_used_as_equity_strategy_input(tmp_path, make_dataset):
    raw, _, _ = snapshots(make_dataset)
    csv, metadata = tmp_path / "raw.csv", tmp_path / "raw.json"
    raw.bars.rename_axis("timestamp").reset_index().to_csv(csv, index=False)
    metadata.write_text(raw.spec.model_dump_json())
    with pytest.raises(ValueError, match="adjusted"):
        load_csv(csv, metadata)
    loaded = load_csv(csv, metadata, allow_raw_for_audit=True)
    with pytest.raises(ValueError, match="audits"):
        features(loaded, defaults("adaptive_pullback"))


def test_cli_success_failure_reports_and_no_overwrite(tmp_path, make_dataset, monkeypatch):
    raw, adjusted, observation = snapshots(make_dataset)
    for label, data in [("raw", raw), ("adjusted", adjusted)]:
        data.bars.rename_axis("timestamp").reset_index().to_csv(
            tmp_path / f"{label}.csv", index=False
        )
        (tmp_path / f"{label}.json").write_text(data.spec.model_dump_json())
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps([observation.model_dump(mode="json")]))
    output = tmp_path / "audit.json"
    arguments = [
        "audit",
        "--raw-csv",
        str(tmp_path / "raw.csv"),
        "--raw-metadata",
        str(tmp_path / "raw.json"),
        "--adjusted-csv",
        str(tmp_path / "adjusted.csv"),
        "--adjusted-metadata",
        str(tmp_path / "adjusted.json"),
        "--actions",
        str(actions),
        "--as-of",
        AS_OF.isoformat(),
        "--output",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    main()
    assert json.loads(output.read_text())["consistent"]
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    actions.write_text("[]")
    failed = tmp_path / "failed-audit.json"
    monkeypatch.setattr(sys, "argv", [*arguments[:-1], str(failed)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert not json.loads(failed.read_text())["consistent"]
