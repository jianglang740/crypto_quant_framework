from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

from crypto_quant.analysis.performance import PerformanceAnalyzer
from crypto_quant.config import BacktestConfig
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.engine.backtest import BacktestEngine
from crypto_quant.enums import PositionSide, TradingMode
from crypto_quant.strategy.base import StrategyBase


class MomentumMovingAverageFuturesStrategy(StrategyBase):
    name = "momentum_moving_average_futures"

    def __init__(
        self,
        short_window: int = 7,
        long_window: int = 14,
        return_window: int = 7,
        return_threshold: Decimal = Decimal("0.005"),
        position_ratio: Decimal = Decimal("0.95"),
    ):
        super().__init__(trading_mode=TradingMode.FUTURE)
        self.short_window = short_window
        self.long_window = long_window
        self.return_window = return_window
        self.return_threshold = return_threshold
        self.position_ratio = position_ratio
        self.closes: deque[Decimal] = deque(maxlen=max(long_window, return_window) + 1)

    def on_bar(self, bar: BarData) -> None:
        self.closes.append(bar.close)
        if len(self.closes) < self.closes.maxlen:
            return

        closes = list(self.closes)
        short_ma_previous = self._mean(closes[-self.short_window - 1:-1])
        long_ma_previous = self._mean(closes[-self.long_window - 1:-1])
        short_ma_current = self._mean(closes[-self.short_window:])
        long_ma_current = self._mean(closes[-self.long_window:])
        n_period_return = bar.close / closes[-self.return_window - 1] - Decimal("1")

        golden_cross = short_ma_previous <= long_ma_previous and short_ma_current > long_ma_current
        death_cross = short_ma_previous >= long_ma_previous and short_ma_current < long_ma_current
        momentum_confirmed = n_period_return >= self.return_threshold

        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        order_amount = self._order_amount(bar.close)

        if golden_cross and momentum_confirmed:
            if not short_position.is_flat:
                self.cover(bar.symbol, abs(short_position.amount))
            if long_position.is_flat:
                self.buy(bar.symbol, order_amount)
            return

        if death_cross:
            if not long_position.is_flat:
                self.close_position(bar.symbol, PositionSide.BOTH)
            if short_position.is_flat:
                self.short(bar.symbol, order_amount)

    def on_stop(self) -> None:
        if self.data is None:
            return
        symbol = self.data.current.symbol
        self.close_position(symbol, PositionSide.BOTH)
        self.close_position(symbol, PositionSide.SHORT)
        self.account.unrealized_pnl = Decimal("0")
        self.account.equity = self.account.cash

    def _mean(self, values: list[Decimal]) -> Decimal:
        return sum(values) / Decimal(len(values))

    def _order_amount(self, price: Decimal) -> Decimal:
        leverage = self.engine.config.leverage if self.engine is not None else Decimal("1")
        return self.account.available * leverage / price * self.position_ratio


def build_demo_data() -> DataFeed:
    bars: list[BarData] = []
    price = Decimal("1000")
    changes = [
        Decimal("-4"), Decimal("-3"), Decimal("-2"), Decimal("-1"), Decimal("1"),
        Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5"), Decimal("6"),
        Decimal("5"), Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1"),
        Decimal("-2"), Decimal("-4"), Decimal("-6"), Decimal("-5"), Decimal("-4"),
        Decimal("-3"), Decimal("-2"), Decimal("2"), Decimal("4"), Decimal("6"),
        Decimal("7"), Decimal("8"), Decimal("6"), Decimal("4"), Decimal("2"),
    ]
    for index, change in enumerate(changes):
        open_price = price
        close_price = price + change
        high_price = max(open_price, close_price) + Decimal("2")
        low_price = min(open_price, close_price) - Decimal("2")
        bars.append(
            BarData(
                symbol="ETH/USDT",
                timeframe="15m",
                datetime=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=Decimal("100"),
            )
        )
        price = close_price
    return DataFeed(bars)


def main() -> None:
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
    result = engine.run(strategy, build_demo_data())
    report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)

    print(result.final_account)
    print(report)
    print(f"orders: {len(result.orders)}")
    print(f"trades: {len(result.trades)}")


if __name__ == "__main__":
    main()
