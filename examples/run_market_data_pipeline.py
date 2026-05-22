from datetime import datetime

from crypto_quant.config import BinanceConfig, MySQLConfig
from crypto_quant.data import MarketDataFetcher, MarketDataPipeline
from crypto_quant.database import MarketDataRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.enums import KlineInterval, TradingMode
from crypto_quant.exchange import BinanceClient


mysql_config = MySQLConfig(
    host="127.0.0.1",
    port=3306,
    username="root",
    password="你的MySQL密码",
    database="crypto_quant",
)

binance_config = BinanceConfig(
    trading_mode=TradingMode.SPOT,
    sandbox=False,
)


def main() -> None:
    mysql_engine = create_mysql_engine(mysql_config)
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)

    client = BinanceClient(binance_config)
    fetcher = MarketDataFetcher(client)

    with Session() as session:
        market_repository = MarketDataRepository(session)
        pipeline = MarketDataPipeline(fetcher, market_repository)
        result = pipeline.fetch_clean_store(
            symbol="BTC/USDT",
            timeframe=KlineInterval.M1,
            start=datetime(2024, 6, 1, 8, 0),
            end=datetime(2024, 6, 1, 9, 0),
            limit=1000,
            request_interval_seconds=0.2,
        )

    print(f"symbol: {result.symbol}")
    print(f"timeframe: {result.timeframe}")
    print(f"fetched bars: {result.fetched_count}")
    print(f"stored bars: {result.stored_count}")
    print(f"data feed bars: {len(result.data_feed)}")
    print(f"missing intervals: {len(result.quality_report.missing_intervals)}")


if __name__ == "__main__":
    main()
