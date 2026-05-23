from decimal import Decimal

from crypto_quant.analysis.bokeh_report import BokehBacktestReport
from crypto_quant.config import BacktestConfig
from crypto_quant.engine.backtest import BacktestEngine
from examples.basic_strategy import MomentumMovingAverageFuturesStrategy, build_demo_data


def main() -> None:
    data = build_demo_data()
    strategy = MomentumMovingAverageFuturesStrategy(
        short_window=3,
        long_window=5,
        return_window=3,
        return_threshold=Decimal("0.003"),
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
    BokehBacktestReport(result, data, title="Demo Backtest Report").save("backtest_report.html")
    print("saved: backtest_report.html")


if __name__ == "__main__":
    main()
