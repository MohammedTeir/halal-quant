"""Provider-neutral, explicitly timestamped research inputs; no network fetching."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DataSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    source: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    asset_class: Literal["stock", "etf", "gold"]
    timeframe_seconds: int = Field(gt=0)
    price_basis: Literal["split_adjusted", "total_return_adjusted", "unadjusted"]
    volume_basis: Literal["as_reported", "split_adjusted"] = "as_reported"
    adjustment_rounding_quantum: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00000001"),
        le=Decimal("0.01"),
        allow_inf_nan=False,
        exclude_if=lambda value: value is None,
    )
    quote_basis: Literal["bid", "ask", "mid", "trade"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    volume_semantics: Literal["provider_reported", "unavailable_zero_placeholder"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    currency: Literal["USD"] = "USD"
    retrieved_at: AwareDatetime
    synthetic: bool = False
    timestamp_semantics: Literal["bar_close"] = "bar_close"


@dataclass
class Dataset:
    bars: pd.DataFrame
    spec: DataSpec
    csv_sha256: str
    metadata_sha256: str

    def manifest(self):
        return {
            "metadata": self.spec.model_dump(mode="json"),
            "csv_sha256": self.csv_sha256,
            "metadata_sha256": self.metadata_sha256,
            "rows": len(self.bars),
            "first_bar_close": self.bars.index[0].isoformat(),
            "last_bar_close": self.bars.index[-1].isoformat(),
        }


def load_csv(
    csv_path: str | Path, metadata_path: str | Path, *, allow_raw_for_audit=False
) -> Dataset:
    raw = Path(csv_path).read_bytes()
    metadata = Path(metadata_path).read_bytes()
    spec = DataSpec.model_validate_json(metadata)
    frame = pd.read_csv(BytesIO(raw))
    required = ["timestamp", "Open", "High", "Low", "Close", "Volume"]
    if list(frame.columns) != required or len(frame) < 3:
        raise ValueError("Expected timestamp,Open,High,Low,Close,Volume and at least three bars")
    # Never silently interpret a naive local timestamp as UTC.
    stamps = [pd.Timestamp(value) for value in frame.pop("timestamp")]
    if any(stamp.tzinfo is None for stamp in stamps):
        raise ValueError("Every bar close needs an explicit timezone")
    index = pd.DatetimeIndex(pd.to_datetime(stamps, utc=True))
    if index.hasnans or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Bar closes must be valid, unique and strictly increasing")
    if index[-1].to_pydatetime() > spec.retrieved_at:
        raise ValueError("Bar closes cannot be later than snapshot retrieval")
    frame.index = index
    frame.index.name = "bar_close"
    frame = frame.apply(pd.to_numeric, errors="raise").astype(float)
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Non-finite market observation")
    if (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError("Prices must be positive")
    if spec.adjustment_rounding_quantum is not None and spec.price_basis != "split_adjusted":
        raise ValueError("Adjustment rounding applies only to split-adjusted snapshots")
    if spec.volume_semantics == "unavailable_zero_placeholder" and (frame.Volume != 0).any():
        raise ValueError("Unavailable volume must use explicitly marked zero placeholders")
    if (frame.Volume < 0).any():
        raise ValueError("Volume must be nonnegative")
    if (
        (frame.Low > frame[["Open", "Close"]].min(axis=1))
        | (frame.High < frame[["Open", "Close"]].max(axis=1))
    ).any():
        raise ValueError("Invalid OHLC bounds")
    if (index.to_series().diff().dropna().dt.total_seconds() < spec.timeframe_seconds).any():
        raise ValueError("Bars overlap the declared timeframe")
    if (
        not allow_raw_for_audit
        and spec.asset_class in ("stock", "etf")
        and spec.price_basis == "unadjusted"
    ):
        raise ValueError("Equity research requires explicitly adjusted OHLC data")
    return Dataset(
        frame, spec, hashlib.sha256(raw).hexdigest(), hashlib.sha256(metadata).hexdigest()
    )


def write_metadata(path: Path, spec: DataSpec):
    path.write_text(json.dumps(spec.model_dump(mode="json"), indent=2) + "\n")
