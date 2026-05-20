from decimal import Decimal

from crypto_quant.analysis.performance import PerformanceAnalyzer
from crypto_quant.config import BacktestConfig
from crypto_quant.data import load_bars_from_csv
from crypto_quant.engine.backtest import BacktestEngine
from examples.basic_strategy import MomentumMovingAverageFuturesStrategy


CSV_PATH = "data/ETH_USDT_USDT_15m.csv"
SYMBOL = "ETH/USDT"
TIMEFRAME = "15m"


def main() -> None:
    data = load_bars_from_csv(
        path=CSV_PATH,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
    )
    strategy = MomentumMovingAverageFuturesStrategy(
        short_window=7,
        long_window=14,
        return_window=7,
        return_threshold=Decimal("0.005"),
    )
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=Decimal("1000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0"),
            leverage=Decimal("50"),
        )
    )
    result = engine.run(strategy, data)
    report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)

    print(result.final_account)
    print(report)
    print(f"orders: {len(result.orders)}")
    print(f"trades: {len(result.trades)}")


if __name__ == "__main__":
    main()
