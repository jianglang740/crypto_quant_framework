from dataclasses import dataclass
from datetime import datetime, timezone

from crypto_quant.data.cleaner import DataQualityReport, clean_and_validate_bars
from crypto_quant.data.feed import DataFeed
from crypto_quant.data.time_utils import BEIJING_TIMEZONE
from crypto_quant.enums import KlineInterval


@dataclass(frozen=True, slots=True)
class MarketDataPipelineResult:
    symbol: str
    timeframe: str
    fetched_count: int
    stored_count: int
    data_feed: DataFeed
    quality_report: DataQualityReport


class MarketDataPipeline:
    def __init__(self, fetcher, repository, exchange: str = "okx"):
        self.fetcher = fetcher
        self.repository = repository
        self.exchange = exchange

    def fetch_clean_store(
        self,
        symbol: str,
        timeframe: KlineInterval | str = KlineInterval.M1,
        start: int | datetime | None = None,
        end: int | datetime | None = None,
        limit: int = 1000,
        request_interval_seconds: float = 0,
        target_timezone: timezone = BEIJING_TIMEZONE,
        input_timezone: timezone = BEIJING_TIMEZONE,
        drop_timezone: bool = False,
        raise_on_missing: bool = False,
    ) -> MarketDataPipelineResult:
        timeframe_value = timeframe.value if isinstance(timeframe, KlineInterval) else timeframe
        fetched_bars = self.fetcher.fetch_ohlcv_range(
            symbol=symbol,
            timeframe=timeframe_value,
            start=start,
            end=end,
            limit=limit,
            request_interval_seconds=request_interval_seconds,
            target_timezone=target_timezone,
            input_timezone=input_timezone,
            drop_timezone=drop_timezone,
        )
        cleaned_bars, quality_report = clean_and_validate_bars(
            fetched_bars,
            target_timezone=target_timezone,
            drop_timezone=drop_timezone,
            expected_timeframe=timeframe_value,
            raise_on_missing=raise_on_missing,
        )
        self.repository.upsert_klines(cleaned_bars, exchange=self.exchange)
        data_feed = self.repository.get_data_feed(
            symbol=symbol,
            timeframe=timeframe_value,
            start=start if isinstance(start, datetime) else None,
            end=end if isinstance(end, datetime) else None,
            exchange=self.exchange,
        )
        return MarketDataPipelineResult(
            symbol=symbol,
            timeframe=timeframe_value,
            fetched_count=len(fetched_bars),
            stored_count=len(cleaned_bars),
            data_feed=data_feed,
            quality_report=quality_report,
        )
