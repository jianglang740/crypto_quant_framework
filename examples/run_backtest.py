from datetime import datetime, timezone
from decimal import Decimal

from crypto_quant.analysis import PerformanceAnalyzer
from crypto_quant.config import BacktestConfig
from crypto_quant.data import BarData, DataFeed
from crypto_quant.engine import BacktestEngine
from crypto_quant.enums import TradingMode
from examples.simple_moving_average_strategy import SimpleMovingAverageStrategy


bars = [
    BarData(
        symbol="BTC/USDT",
        timeframe="1m",
        datetime=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
        open=Decimal("100000") + Decimal(index),
        high=Decimal("100010") + Decimal(index),
        low=Decimal("99990") + Decimal(index),
        close=Decimal("100000") + Decimal(index),
        volume=Decimal("10"),
    )
    for index in range(60)
]

strategy = SimpleMovingAverageStrategy(trading_mode=TradingMode.SPOT)
engine = BacktestEngine(BacktestConfig(initial_cash=Decimal("10000")))
result = engine.run(strategy, DataFeed(bars))
report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)

print(result.final_account)
print(report)
