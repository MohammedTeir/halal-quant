import json
import sys

import pytest

from services.backtesting.cli import main
from services.market_data.csv_data import write_metadata
from tests.backtesting.test_strategies import config


def test_cli_writes_strict_json_and_preserves_existing_report(tmp_path, make_dataset, monkeypatch):
    data = make_dataset(asset="etf")
    csv, metadata = tmp_path / "etf.csv", tmp_path / "etf.meta.json"
    data.bars.rename_axis("timestamp").reset_index().to_csv(csv, index=False)
    write_metadata(metadata, data.spec)
    benchmark_csv, benchmark_meta = tmp_path / "benchmark.csv", tmp_path / "benchmark.json"
    data.bars.rename_axis("timestamp").reset_index().to_csv(benchmark_csv, index=False)
    write_metadata(benchmark_meta, data.spec.model_copy(update={"symbol": "BENCHMARK"}))
    parameters = tmp_path / "strategy.json"
    parameters.write_text(config("regime_trend").model_dump_json())
    output = tmp_path / "report.json"
    argv = [
        "research",
        "--strategy",
        "regime_trend",
        "--csv",
        str(csv),
        "--metadata",
        str(metadata),
        "--benchmark-csv",
        str(benchmark_csv),
        "--benchmark-metadata",
        str(benchmark_meta),
        "--strategy-config",
        str(parameters),
        "--output",
        str(output),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    first = output.read_bytes()
    report = json.loads(first, parse_constant=lambda v: pytest.fail(f"Nonstandard JSON: {v}"))
    assert report["windows"]["holdout"]["strategy"]["trade_count"] > 0
    assert not report["authorized_for_paper"]
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert output.read_bytes() == first
    # Same files and settings yield byte-identical reports at a different output path.
    monkeypatch.setattr(sys, "argv", [*argv[:-1], str(tmp_path / "repeat.json")])
    main()
    assert (tmp_path / "repeat.json").read_bytes() == first


def test_cli_requires_both_benchmark_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "research",
            "--strategy",
            "regime_trend",
            "--csv",
            "unused",
            "--metadata",
            "unused",
            "--benchmark-csv",
            "one-file",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not (tmp_path / "report.json").exists()
