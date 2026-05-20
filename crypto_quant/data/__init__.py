from crypto_quant.data.feed import BarData, DataFeed, DataLine

__all__ = ["BarData", "DataFeed", "DataLine", "MarketDataFetcher", "load_bars_from_csv"]


def __getattr__(name: str):
    if name == "MarketDataFetcher":
        from crypto_quant.data.fetcher import MarketDataFetcher

        return MarketDataFetcher
    if name == "load_bars_from_csv":
        from crypto_quant.data.csv_loader import load_bars_from_csv

        return load_bars_from_csv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")