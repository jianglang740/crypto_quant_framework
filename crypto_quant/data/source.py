from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crypto_quant.data.csv_loader import load_bars_from_csv
from crypto_quant.data.feed import DataFeed
from crypto_quant.data.time_utils import BEIJING_TIMEZONE
from crypto_quant.enums import KlineInterval


class DataSource:
    @staticmethod
    def from_csv(
        path: str | Path,
        symbol: str,
        timeframe: str,
        source_timezone: timezone = BEIJING_TIMEZONE,
        target_timezone: timezone = BEIJING_TIMEZONE,
        drop_timezone: bool = False,
        **kwargs: Any,
    ) -> DataFeed:
        return load_bars_from_csv(
            path=path,
            symbol=symbol,
            timeframe=timeframe,
            source_timezone=source_timezone,
            target_timezone=target_timezone,
            drop_timezone=drop_timezone,
            **kwargs,
        )

    @staticmethod
    def from_binance(
        fetcher: Any,
        symbol: str,
        timeframe: KlineInterval | str = KlineInterval.M1,
        start: int | datetime | None = None,
        end: int | datetime | None = None,
        target_timezone: timezone = BEIJING_TIMEZONE,
        input_timezone: timezone = BEIJING_TIMEZONE,
        drop_timezone: bool = False,
        **kwargs: Any,
    ) -> DataFeed:
        return fetcher.fetch_data_feed(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            target_timezone=target_timezone,
            input_timezone=input_timezone,
            drop_timezone=drop_timezone,
            **kwargs,
        )

    @staticmethod
    def from_database(
        repository: Any,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        exchange: str = "binance",
        limit: int | None = None,
    ) -> DataFeed:
        return repository.get_data_feed(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            exchange=exchange,
            limit=limit,
        )
