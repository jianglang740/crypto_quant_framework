from datetime import datetime
from decimal import Decimal
from getpass import getpass

from crypto_quant.config import BacktestConfig, BinanceConfig, MySQLConfig
from crypto_quant.data import MarketDataFetcher, MarketDataPipeline
from crypto_quant.database import MarketDataRepository, TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.engine.backtest import BacktestEngine
from crypto_quant.enums import KlineInterval, TradingMode
from crypto_quant.exchange import BinanceClient
from examples.simple_moving_average_strategy import SimpleMovingAverageStrategy


SYMBOL = "BTC/USDT"
TIMEFRAME = KlineInterval.M1
START = datetime(2024, 6, 1, 8, 0)
END = datetime(2024, 6, 1, 10, 0)


mysql_config = MySQLConfig(
    host="127.0.0.1",
    port=3306,
    username="crypto_quant_user",
    password=getpass("请输入本地 MySQL 密码："),
    database="crypto_quant",
)

binance_config = BinanceConfig(
    trading_mode=TradingMode.SPOT,
    sandbox=False,
    proxies={
        "http": "socks5h://127.0.0.1:1080",
        "https": "socks5h://127.0.0.1:1080",
    },
)


def main() -> None:
    mysql_engine = create_mysql_engine(mysql_config)
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)

    client = BinanceClient(binance_config)
    fetcher = MarketDataFetcher(client)

    with Session() as session:
        market_repository = MarketDataRepository(session)
        trading_repository = TradingRepository(session)
        pipeline = MarketDataPipeline(fetcher, market_repository)

        pipeline_result = pipeline.fetch_clean_store(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start=START,
            end=END,
            limit=1000,
            request_interval_seconds=0.2,
        )

        strategy = SimpleMovingAverageStrategy(
            fast_window=5,
            slow_window=20,
            trading_mode=TradingMode.SPOT,
        )
        backtest_engine = BacktestEngine(
            BacktestConfig(
                initial_cash=Decimal("10000"),
                commission_rate=Decimal("0.0004"),
                slippage_rate=Decimal("0"),
                allow_short=False,
            )
        )
        backtest_result = backtest_engine.run(strategy, pipeline_result.data_feed)
        run = trading_repository.save_backtest_result(
            backtest_result,
            strategy_name=strategy.name,
            trading_mode=TradingMode.SPOT.value,
            run_name="market_data_pipeline_backtest",
            config={
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME.value,
                "start": START,
                "end": END,
                "source": "examples/run_market_data_pipeline.py",
            },
        )

        orders = trading_repository.get_orders(run.run_id)
        trades = trading_repository.get_trades(run.run_id)
        equity_curve = trading_repository.get_equity_curve(run.run_id)

    print("完整数据库闭环验证完成")
    print(f"symbol: {pipeline_result.symbol}")
    print(f"timeframe: {pipeline_result.timeframe}")
    print(f"Binance 拉取 K线数量: {pipeline_result.fetched_count}")
    print(f"清洗后入库 K线数量: {pipeline_result.stored_count}")
    print(f"从 MySQL 读回 DataFeed 数量: {len(pipeline_result.data_feed)}")
    print(f"缺失区间数量: {len(pipeline_result.quality_report.missing_intervals)}")
    print(f"回测订单数量: {len(orders)}")
    print(f"回测成交数量: {len(trades)}")
    print(f"权益曲线点数: {len(equity_curve)}")
    print(f"回测结果 run_id: {run.run_id}")
    print(f"回测结果状态: {run.status}")
    print(f"最终权益: {run.final_equity}")


if __name__ == "__main__":
    main()
