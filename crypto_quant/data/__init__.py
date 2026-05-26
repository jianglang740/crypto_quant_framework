from crypto_quant.data.cleaner import DataQualityReport, clean_and_validate_bars, clean_bars, parse_bar_datetime, validate_bars
from crypto_quant.data.feed import BarData, DataFeed, DataLine
from crypto_quant.data.time_utils import BEIJING_TIMEZONE, UTC_TIMEZONE, datetime_to_milliseconds, timestamp_to_datetime, to_milliseconds

__all__ = [
    "BEIJING_TIMEZONE",
    "UTC_TIMEZONE",
    "BarData",
    "DataFeed",
    "DataLine",
    "DataQualityReport",
    "DataSource",
    "MarketDataFetcher",
    "MarketDataPipeline",
    "MarketDataPipelineResult",
    "clean_and_validate_bars",
    "clean_bars",
    "datetime_to_milliseconds",
    "load_bars_from_csv",
    "parse_bar_datetime",
    "timestamp_to_datetime",
    "to_milliseconds",
    "validate_bars",
]


def __getattr__(name: str):
    if name == "DataSource":
        from crypto_quant.data.source import DataSource

        return DataSource
    if name == "MarketDataFetcher":
        from crypto_quant.data.fetcher import MarketDataFetcher

        return MarketDataFetcher
    if name in {"MarketDataPipeline", "MarketDataPipelineResult"}:
        from crypto_quant.data.pipeline import MarketDataPipeline, MarketDataPipelineResult

        return {"MarketDataPipeline": MarketDataPipeline, "MarketDataPipelineResult": MarketDataPipelineResult}[name]
    if name == "load_bars_from_csv":
        from crypto_quant.data.csv_loader import load_bars_from_csv

        return load_bars_from_csv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")