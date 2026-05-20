from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_quant.data.feed import BarData, DataFeed


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
) -> DataFeed:
    df = pd.read_csv(path)
    required_columns = [datetime_column, open_column, high_column, low_column, close_column]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV missing required columns: {missing_columns}")

    df = df.copy()
    df[datetime_column] = pd.to_datetime(df[datetime_column])
    if volume_column not in df.columns:
        df[volume_column] = 0

    price_columns = [open_column, high_column, low_column, close_column, volume_column]
    df[price_columns] = df[price_columns].apply(pd.to_numeric, errors="coerce")
    invalid_mask = ~np.isfinite(df[price_columns].to_numpy(dtype=float)).all(axis=1)
    if invalid_mask.any():
        invalid_rows = df.index[invalid_mask].tolist()[:10]
        raise ValueError(f"CSV contains invalid numeric values at rows: {invalid_rows}")

    df = df.sort_values(datetime_column)
    bars = [
        BarData(
            symbol=symbol,
            timeframe=timeframe,
            datetime=_to_datetime(row[datetime_column]),
            open=Decimal(str(row[open_column])),
            high=Decimal(str(row[high_column])),
            low=Decimal(str(row[low_column])),
            close=Decimal(str(row[close_column])),
            volume=Decimal(str(row[volume_column])),
        )
        for _, row in df.iterrows()
    ]
    return DataFeed(bars)


def _to_datetime(value: object) -> datetime:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return pd.to_datetime(value).to_pydatetime()
