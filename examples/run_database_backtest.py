from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from crypto_quant.config import BacktestConfig
from crypto_quant.database import Base, Kline, MarketDataRepository, TradingRepository
from crypto_quant.engine.backtest import BacktestEngine
from crypto_quant.enums import TradingMode
from examples.basic_strategy import MomentumMovingAverageFuturesStrategy, build_demo_data


engine = create_engine("sqlite:///:memory:", future=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def main() -> None:
    session = Session()
    market_repository = MarketDataRepository(session)
    trading_repository = TradingRepository(session)

    source_data = build_demo_data()
    for bar in source_data.bars:
        session.add(
            Kline(
                exchange="okx",
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                open_time=bar.datetime.replace(tzinfo=None),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
    session.commit()
    data = market_repository.get_data_feed("ETH/USDT", "15m")

    strategy = MomentumMovingAverageFuturesStrategy(
        short_window=3,
        long_window=5,
        return_window=3,
        return_threshold=Decimal("0.003"),
    )
    backtest_engine = BacktestEngine(
        BacktestConfig(
            initial_cash=Decimal("1000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0"),
            leverage=Decimal("50"),
        )
    )
    result = backtest_engine.run(strategy, data)
    run = trading_repository.save_backtest_result(
        result,
        strategy_name=strategy.name,
        trading_mode=TradingMode.FUTURE.value,
        run_name="database_demo_backtest",
        config={"source": "examples/run_database_backtest.py"},
    )

    runs = trading_repository.list_runs(limit=5)
    orders = trading_repository.get_orders(run.run_id)
    trades = trading_repository.get_trades(run.run_id)
    equity_curve = trading_repository.get_equity_curve(run.run_id)

    print(f"saved run_id: {run.run_id}")
    print(f"recent runs: {len(runs)}")
    print(f"orders: {len(orders)}")
    print(f"trades: {len(trades)}")
    print(f"equity points: {len(equity_curve)}")
    print(f"final equity: {run.final_equity}")


if __name__ == "__main__":
    main()
