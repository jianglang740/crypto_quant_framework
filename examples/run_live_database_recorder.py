from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from crypto_quant.database import Base, LiveDatabaseRecorder, TradingRepository
from crypto_quant.engine.live import LiveEngine
from crypto_quant.enums import TradingMode
from examples.basic_strategy import MomentumMovingAverageFuturesStrategy


engine = create_engine("sqlite:///:memory:", future=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class DemoClient:
    pass


def main() -> None:
    session = Session()
    trading_repository = TradingRepository(session)

    strategy = MomentumMovingAverageFuturesStrategy(
        short_window=3,
        long_window=5,
        return_window=3,
        return_threshold=Decimal("0.003"),
    )
    strategy.trading_mode = TradingMode.FUTURE
    live_engine = LiveEngine(DemoClient())
    strategy.bind_engine(live_engine)
    live_engine._initialize_strategy_state(strategy)

    recorder = LiveDatabaseRecorder(
        trading_repository,
        run_name="demo_live_database_recorder",
    )
    run = recorder.start_run(strategy, symbols=["ETH/USDT"], config={"source": "examples/run_live_database_recorder.py"})
    recorder.record_snapshot(strategy)
    recorder.finish_run(strategy)

    print(f"saved run_id: {run.run_id}")
    print(f"account snapshots: {len(trading_repository.get_account_snapshots(run.run_id))}")
    print(f"position snapshots: {len(trading_repository.get_position_snapshots(run.run_id))}")
    print(f"orders: {len(trading_repository.get_orders(run.run_id))}")


if __name__ == "__main__":
    main()
