import json

import pytest

from services.market_data.csv_data import load_csv


def files(tmp_path, dataset):
    csv, meta = tmp_path / "bars.csv", tmp_path / "bars.json"
    dataset.bars.rename_axis("timestamp").reset_index().to_csv(csv, index=False)
    meta.write_text(dataset.spec.model_dump_json())
    return csv, meta


def test_csv_provenance_and_utc(tmp_path, make_dataset):
    csv, meta = files(tmp_path, make_dataset(count=10))
    result = load_csv(csv, meta)
    assert str(result.bars.index.tz) == "UTC"
    assert result.manifest()["rows"] == 10
    assert len(result.csv_sha256) == len(result.metadata_sha256) == 64
    assert load_csv(csv, meta).manifest() == result.manifest()


@pytest.mark.parametrize(
    "case",
    ["duplicate", "unsorted", "naive", "negative", "bounds", "infinity", "missing", "volume"],
)
def test_bad_csv_rejected(tmp_path, make_dataset, case):
    dataset = make_dataset(count=10)
    frame = dataset.bars
    if case == "duplicate":
        frame.index = [frame.index[0]] * len(frame)
    elif case == "unsorted":
        frame = frame.iloc[::-1]
    elif case == "naive":
        frame.index = frame.index.tz_localize(None)
    elif case == "negative":
        frame.iloc[2, frame.columns.get_loc("Close")] = -1
    elif case == "bounds":
        frame.iloc[2, frame.columns.get_loc("High")] = 1
    elif case == "infinity":
        frame.iloc[2, frame.columns.get_loc("Close")] = float("inf")
    elif case == "missing":
        frame = frame.drop(columns="Volume")
    elif case == "volume":
        frame.iloc[2, frame.columns.get_loc("Volume")] = -1
    dataset.bars = frame
    csv, meta = files(tmp_path, dataset)
    with pytest.raises(ValueError):
        load_csv(csv, meta)


def test_unadjusted_equity_and_unknown_provenance_fields_rejected(tmp_path, make_dataset):
    csv, meta = files(tmp_path, make_dataset(count=10))
    metadata = json.loads(meta.read_text())
    metadata["price_basis"] = "unadjusted"
    meta.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="adjusted"):
        load_csv(csv, meta)
    metadata["price_basis"] = "split_adjusted"
    metadata["compliance_approved"] = True
    meta.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        load_csv(csv, meta)
