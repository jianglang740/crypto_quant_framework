from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_quant.data.cleaner import clean_and_validate_bars, parse_bar_datetime
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.data.time_utils import BEIJING_TIMEZONE


def load_bars_from_csv(
    path: str | Path,
    symbol: str,
    timeframe: str,
    datetime_column: str = "datetime",
    open_column: str = "open",
    high_column: str = "high",
    low_column: str = "low",
    close_column: str = "close",
    volume_column: str = "volume",
    source_timezone: timezone = BEIJING_TIMEZONE,
    target_timezone: timezone = BEIJING_TIMEZONE,
    drop_timezone: bool = False,
    validate: bool = True,
    raise_on_missing: bool = False,
) -> DataFeed:
    df = pd.read_csv(path)
    required_columns = [datetime_column, open_column, high_column, low_column, close_column]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV missing required columns: {missing_columns}")

    df = df.copy()
    if volume_column not in df.columns:
        df[volume_column] = 0

    price_columns = [open_column, high_column, low_column, close_column, volume_column]
    df[price_columns] = df[price_columns].apply(pd.to_numeric, errors="coerce")
    invalid_mask = ~np.isfinite(df[price_columns].to_numpy(dtype=float)).all(axis=1)
    if invalid_mask.any():
        invalid_rows = df.index[invalid_mask].tolist()[:10]
        raise ValueError(f"CSV contains invalid numeric values at rows: {invalid_rows}")

    bars = [
        BarData(
            symbol=symbol,
            timeframe=timeframe,
            datetime=parse_bar_datetime(
                _to_datetime(row[datetime_column]),
                source_timezone=source_timezone,
                target_timezone=target_timezone,
                drop_timezone=drop_timezone,
            ),
            open=Decimal(str(row[open_column])),
            high=Decimal(str(row[high_column])),
            low=Decimal(str(row[low_column])),
            close=Decimal(str(row[close_column])),
            volume=Decimal(str(row[volume_column])),
        )
        for _, row in df.iterrows()
    ]
    if validate:
        bars, _ = clean_and_validate_bars(
            bars,
            target_timezone=target_timezone,
            drop_timezone=drop_timezone,
            expected_timeframe=timeframe,
            raise_on_missing=raise_on_missing,
        )
    return DataFeed(bars)


def _to_datetime(value: object) -> datetime | int | float | Decimal:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, datetime | int | float | Decimal):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return pd.to_datetime(value).to_pydatetime()
