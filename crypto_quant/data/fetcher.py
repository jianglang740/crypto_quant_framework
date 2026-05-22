from datetime import datetime, timezone
from decimal import Decimal
from time import sleep
from typing import Any

from crypto_quant.data.cleaner import clean_bars
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.data.time_utils import BEIJING_TIMEZONE, timestamp_to_datetime, to_milliseconds
from crypto_quant.enums import KlineInterval
from crypto_quant.exchange.binance_client import BinanceClient


class MarketDataFetcher:
    def __init__(self, client: BinanceClient):
        self.client = client

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: KlineInterval | str = KlineInterval.M1,
        since: int | datetime | None = None,
        limit: int | None = 500,
        params: dict[str, Any] | None = None,
        target_timezone: timezone = BEIJING_TIMEZONE,
        since_timezone: timezone = BEIJING_TIMEZONE,
        drop_timezone: bool = False,
    ) -> list[BarData]:
        timeframe_value = timeframe.value if isinstance(timeframe, KlineInterval) else timeframe
        since_ms = to_milliseconds(since, source_timezone=since_timezone)
        rows = self.client.exchange.fetch_ohlcv(symbol, timeframe_value, since_ms, limit, params or {})
        return self._rows_to_bars(symbol, timeframe_value, rows, target_timezone, drop_timezone)

    def fetch_ohlcv_range(
        self,
        symbol: str,
        timeframe: KlineInterval | str = KlineInterval.M1,
        start: int | datetime | None = None,
        end: int | datetime | None = None,
        limit: int = 1000,
        params: dict[str, Any] | None = None,
        request_interval_seconds: float = 0,
        target_timezone: timezone = BEIJING_TIMEZONE,
        input_timezone: timezone = BEIJING_TIMEZONE,
        drop_timezone: bool = False,
    ) -> list[BarData]:
        timeframe_value = timeframe.value if isinstance(timeframe, KlineInterval) else timeframe
        since_ms = to_milliseconds(start, source_timezone=input_timezone)
        end_ms = to_milliseconds(end, source_timezone=input_timezone)
        all_bars: list[BarData] = []
        while True:
            rows = self.client.exchange.fetch_ohlcv(symbol, timeframe_value, since_ms, limit, params or {})
            if not rows:
                break
            bars = self._rows_to_bars(symbol, timeframe_value, rows, target_timezone, drop_timezone)
            if end_ms is not None:
                bars = [bar for bar in bars if to_milliseconds(bar.datetime, source_timezone=target_timezone) <= end_ms]
            all_bars.extend(bars)
            last_open_time = int(rows[-1][0])
            next_since = last_open_time + 1
            if end_ms is not None and next_since > end_ms:
                break
            if since_ms is not None and next_since <= since_ms:
                break
            if len(rows) < limit:
                break
            since_ms = next_since
            if request_interval_seconds > 0:
                sleep(request_interval_seconds)
        return clean_bars(all_bars, target_timezone=target_timezone, drop_timezone=drop_timezone)

    def fetch_data_feed(
        self,
        symbol: str,
        timeframe: KlineInterval | str = KlineInterval.M1,
        start: int | datetime | None = None,
        end: int | datetime | None = None,
        limit: int = 1000,
        params: dict[str, Any] | None = None,
        target_timezone: timezone = BEIJING_TIMEZONE,
        input_timezone: timezone = BEIJING_TIMEZONE,
        drop_timezone: bool = False,
    ) -> DataFeed:
        return DataFeed(
            self.fetch_ohlcv_range(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
                params=params,
                target_timezone=target_timezone,
                input_timezone=input_timezone,
                drop_timezone=drop_timezone,
            )
        )

    def fetch_ticker(self, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.exchange.fetch_ticker(symbol, params or {})

    def fetch_tickers(self, symbols: list[str] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.exchange.fetch_tickers(symbols, params or {})

    def fetch_order_book(self, symbol: str, limit: int | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.exchange.fetch_order_book(symbol, limit, params or {})

    def fetch_trades(self, symbol: str, since: int | None = None, limit: int | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.client.exchange.fetch_trades(symbol, since, limit, params or {})

    def fetch_funding_rate(self, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.exchange.fetch_funding_rate(symbol, params or {})

    def fetch_funding_rate_history(
        self,
        symbol: str,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.client.exchange.fetch_funding_rate_history(symbol, since, limit, params or {})

    def _rows_to_bars(
        self,
        symbol: str,
        timeframe: str,
        rows: list[list[Any]],
        target_timezone: timezone,
        drop_timezone: bool,
    ) -> list[BarData]:
        return [
            BarData(
                symbol=symbol,
                timeframe=timeframe,
                datetime=timestamp_to_datetime(row[0], target_timezone=target_timezone, drop_timezone=drop_timezone),
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )
            for row in rows
        ]
