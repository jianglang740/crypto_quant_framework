from collections import deque
from decimal import Decimal

from crypto_quant.analysis import PerformanceAnalyzer
from crypto_quant.analysis.bokeh_report import BokehBacktestReport
from crypto_quant.config import BacktestConfig
from crypto_quant.data import BarData, load_bars_from_csv
from crypto_quant.engine.portfolio_backtest import PortfolioBacktestEngine
from crypto_quant.enums import PositionSide, TradingMode
from crypto_quant.strategy import StrategyBase


CSV_PATH = "/Users/clinking/开发/quant/data/ETH_USDT_5m_1year.csv"
SYMBOL = "ETH/USDT"
TIMEFRAME = "15m"


class MomentumTrendFuturesStrategy(StrategyBase):
    name = "momentum_trend_futures"

    def __init__(
        self,
        short_window: int = 10,
        long_window: int = 30,
        return_window: int = 4,
        return_threshold: Decimal = Decimal("0.003"),
        min_ma_gap: Decimal = Decimal("0.002"),
        stop_loss_rate: Decimal = Decimal("0.015"),
        position_ratio: Decimal = Decimal("0.05"),
    ):
        super().__init__(trading_mode=TradingMode.FUTURE)
        self.short_window = short_window
        self.long_window = long_window
        self.return_window = return_window
        self.return_threshold = return_threshold
        self.min_ma_gap = min_ma_gap
        self.stop_loss_rate = stop_loss_rate
        self.position_ratio = position_ratio
        self.trend_state = "neutral"
        self.closes: deque[Decimal] = deque(maxlen=max(short_window, long_window, return_window) + 1)

    def on_bar(self, bar: BarData) -> None:
        self.closes.append(bar.close)
        if len(self.closes) < self.closes.maxlen:
            return

        closes = list(self.closes)
        short_ma_previous = self._mean(closes[-self.short_window - 1:-1])
        long_ma_previous = self._mean(closes[-self.long_window - 1:-1])
        short_ma_current = self._mean(closes[-self.short_window:])
        long_ma_current = self._mean(closes[-self.long_window:])
        period_return = bar.close / closes[-self.return_window - 1] - Decimal("1")
        ma_gap = abs(short_ma_current / long_ma_current - Decimal("1"))

        self._update_trend_state(short_ma_current, long_ma_current, ma_gap)

        if self._check_stop_loss(bar):
            return

        golden_cross = short_ma_previous <= long_ma_previous and short_ma_current > long_ma_current
        death_cross = short_ma_previous >= long_ma_previous and short_ma_current < long_ma_current
        trend_confirmed = ma_gap >= self.min_ma_gap
        long_signal = golden_cross and period_return >= self.return_threshold and trend_confirmed
        short_signal = death_cross and period_return <= -self.return_threshold and trend_confirmed

        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)

        if long_signal:
            if not short_position.is_flat:
                self.cover(bar.symbol, abs(short_position.amount))
            if long_position.is_flat:
                self.buy(bar.symbol, self._order_amount(bar.close))
            return

        if short_signal:
            if not long_position.is_flat:
                self.close_position(bar.symbol, PositionSide.BOTH)
            if short_position.is_flat:
                self.short(bar.symbol, self._order_amount(bar.close))

    def on_stop(self) -> None:
        if self.data is None or len(self.data) == 0:
            return
        symbol = self.data.current.symbol
        self.close_position(symbol, PositionSide.BOTH)
        self.close_position(symbol, PositionSide.SHORT)

    def _check_stop_loss(self, bar: BarData) -> bool:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not long_position.is_flat and long_position.entry_price > 0:
            pnl_rate = bar.close / long_position.entry_price - Decimal("1")
            if pnl_rate <= -self.stop_loss_rate:
                self.close_position(bar.symbol, PositionSide.BOTH)
                return True
        if not short_position.is_flat and short_position.entry_price > 0:
            pnl_rate = short_position.entry_price / bar.close - Decimal("1")
            if pnl_rate <= -self.stop_loss_rate:
                self.cover(bar.symbol, abs(short_position.amount))
                return True
        return False

    def _update_trend_state(self, short_ma: Decimal, long_ma: Decimal, ma_gap: Decimal) -> None:
        if ma_gap < self.min_ma_gap:
            self.trend_state = "neutral"
        elif short_ma > long_ma:
            self.trend_state = "up"
        elif short_ma < long_ma:
            self.trend_state = "down"
        else:
            self.trend_state = "neutral"

    def _mean(self, values: list[Decimal]) -> Decimal:
        return sum(values) / Decimal(len(values))

    def _order_amount(self, price: Decimal) -> Decimal:
        leverage = self.engine.config.leverage if self.engine is not None else Decimal("1")
        amount = self.account.available * leverage * self.position_ratio / price
        return max(amount, Decimal("0"))


class TrendFilteredRollingReturnReversionFuturesStrategy(StrategyBase):
    name = "trend_filtered_rolling_return_reversion_futures"

    def __init__(
        self,
        trend_strategy: MomentumTrendFuturesStrategy,
        nk: int = 14,
        threshold: Decimal = Decimal("0.07"),
        take_profit_rate: Decimal = Decimal("0.018"),
        stop_loss_rate: Decimal = Decimal("0.033"),
        position_ratio: Decimal = Decimal("0.10"),
    ):
        super().__init__(trading_mode=TradingMode.FUTURE)
        self.trend_strategy = trend_strategy
        self.nk = nk
        self.threshold = threshold
        self.take_profit_rate = take_profit_rate
        self.stop_loss_rate = stop_loss_rate
        self.position_ratio = position_ratio
        self.closes: deque[Decimal] = deque(maxlen=nk + 1)

    def on_bar(self, bar: BarData) -> None:
        self.closes.append(bar.close)
        if len(self.closes) < self.closes.maxlen:
            return

        signal = self._rolling_return_signal()
        signal = self._filter_signal_by_trend(signal)

        if self._check_take_profit_stop_loss(bar):
            return

        if signal == 1:
            self._reverse_to_long(bar)
        elif signal == -1:
            self._reverse_to_short(bar)

    def on_stop(self) -> None:
        if self.data is None or len(self.data) == 0:
            return
        symbol = self.data.current.symbol
        self.close_position(symbol, PositionSide.BOTH)
        self.close_position(symbol, PositionSide.SHORT)

    def _rolling_return_signal(self) -> int:
        closes = list(self.closes)
        rolling_return = closes[-1] / closes[0] - Decimal("1")
        if rolling_return >= self.threshold:
            return -1
        if rolling_return <= -self.threshold:
            return 1
        return 0

    def _filter_signal_by_trend(self, signal: int) -> int:
        if self.trend_strategy.trend_state == "up" and signal == -1:
            return 0
        if self.trend_strategy.trend_state == "down" and signal == 1:
            return 0
        return signal

    def _check_take_profit_stop_loss(self, bar: BarData) -> bool:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not long_position.is_flat and long_position.entry_price > 0:
            pnl_rate = bar.close / long_position.entry_price - Decimal("1")
            if pnl_rate >= self.take_profit_rate or pnl_rate <= -self.stop_loss_rate:
                self.close_position(bar.symbol, PositionSide.BOTH)
                return True
        if not short_position.is_flat and short_position.entry_price > 0:
            pnl_rate = short_position.entry_price / bar.close - Decimal("1")
            if pnl_rate >= self.take_profit_rate or pnl_rate <= -self.stop_loss_rate:
                self.cover(bar.symbol, abs(short_position.amount))
                return True
        return False

    def _reverse_to_long(self, bar: BarData) -> None:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not short_position.is_flat:
            self.cover(bar.symbol, abs(short_position.amount))
        if long_position.is_flat:
            self.buy(bar.symbol, self._order_amount(bar.close))

    def _reverse_to_short(self, bar: BarData) -> None:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not long_position.is_flat:
            self.close_position(bar.symbol, PositionSide.BOTH)
        if short_position.is_flat:
            self.short(bar.symbol, self._order_amount(bar.close))

    def _order_amount(self, price: Decimal) -> Decimal:
        leverage = self.engine.config.leverage if self.engine is not None else Decimal("1")
        amount = self.account.available * leverage * self.position_ratio / price
        return max(amount, Decimal("0"))


def main() -> None:
    data = load_bars_from_csv(
        path=CSV_PATH,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
    )

    trend_strategy = MomentumTrendFuturesStrategy(
        short_window=10,
        long_window=30,
        return_window=4,
        return_threshold=Decimal("0.003"),
        min_ma_gap=Decimal("0.002"),
        stop_loss_rate=Decimal("0.015"),
        position_ratio=Decimal("0.05"),
    )
    reversion_strategy = TrendFilteredRollingReturnReversionFuturesStrategy(
        trend_strategy=trend_strategy,
        nk=14,
        threshold=Decimal("0.07"),
        take_profit_rate=Decimal("0.018"),
        stop_loss_rate=Decimal("0.033"),
        position_ratio=Decimal("0.10"),
    )
    strategies = [trend_strategy, reversion_strategy]
    engine = PortfolioBacktestEngine(
        BacktestConfig(
            initial_cash=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0"),
            leverage=Decimal("10"),
        )
    )
    result = engine.run(strategies, data)
    report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)
    BokehBacktestReport(
        result,
        data,
        title="Momentum Trend + Trend Filtered Rolling Reversion Portfolio Report",
    ).save("swap_portfolio_backtest_report.html")

    print("========== 趋势 + 趋势过滤反转组合 CSV 回测 ==========")
    print(result.final_account)
    print(report)
    print(f"orders: {len(result.orders)}")
    print(f"trades: {len(result.trades)}")
    for strategy_name in result.strategy_trades:
        print(
            f"{strategy_name}: "
            f"orders={len(result.strategy_orders[strategy_name])}, "
            f"trades={len(result.strategy_trades[strategy_name])}"
        )


if __name__ == "__main__":
    main()
