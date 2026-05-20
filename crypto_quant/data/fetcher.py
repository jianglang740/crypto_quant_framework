from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from crypto_quant.data.feed import BarData
from crypto_quant.enums import KlineInterval
from crypto_quant.exchange.binance_client import BinanceClient


class MarketDataFetcher:
    def __init__(self, client: BinanceClient):
        self.client = client

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: KlineInterval | str = KlineInterval.M1,
        since: int | None = None,
        limit: int | None = 500,
        params: dict[str, Any] | None = None,
    ) -> list[BarData]:
        timeframe_value = timeframe.value if isinstance(timeframe, KlineInterval) else timeframe
        rows = self.client.exchange.fetch_ohlcv(symbol, timeframe_value, since, limit, params or {})
        return [
            BarData(
                symbol=symbol,
                timeframe=timeframe_value,
                datetime=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )
            for row in rows
        ]

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
