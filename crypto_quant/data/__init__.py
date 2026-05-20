from crypto_quant.data.feed import BarData, DataFeed, DataLine

__all__ = ["BarData", "DataFeed", "DataLine", "MarketDataFetcher"]


def __getattr__(name: str):
    if name == "MarketDataFetcher":
        from crypto_quant.data.fetcher import MarketDataFetcher

        return MarketDataFetcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")