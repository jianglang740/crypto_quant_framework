from crypto_quant.config import ExchangeConfig, LiveConfig
from crypto_quant.engine import LiveEngine
from crypto_quant.enums import KlineInterval, TradingMode
from crypto_quant.exchange import ExchangeClient
from crypto_quant.data import DataFeed, MarketDataFetcher
from examples.simple_moving_average_strategy import SimpleMovingAverageStrategy


config = ExchangeConfig(trading_mode=TradingMode.SPOT, sandbox=True)
client = ExchangeClient(config)
fetcher = MarketDataFetcher(client)
strategy = SimpleMovingAverageStrategy(trading_mode=TradingMode.SPOT)
engine = LiveEngine(client, LiveConfig(dry_run=True, poll_interval_seconds=10))


def latest_bars() -> DataFeed:
    return DataFeed(fetcher.fetch_ohlcv("BTC/USDT", KlineInterval.M1, limit=100))


if __name__ == "__main__":
    engine.run(strategy, latest_bars)
