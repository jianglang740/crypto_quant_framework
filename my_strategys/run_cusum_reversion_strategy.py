from decimal import Decimal

import numpy as np
from crypto_quant.analysis.bokeh_report import BokehBacktestReport
from crypto_quant.analysis import PerformanceAnalyzer
from crypto_quant.config import BacktestConfig
from crypto_quant.data import BarData, load_bars_from_csv
from crypto_quant.engine import BacktestEngine
from crypto_quant.enums import PositionSide, TradingMode
from crypto_quant.strategy import StrategyBase


CSV_PATH = "/Users/clinking/开发/quant/data/ETH_USDT_5m_1year.csv"
SYMBOL = "ETH/USDT"
TIMEFRAME = "5m"


class RollingReturnReversionFuturesStrategy(StrategyBase):
    name = "rolling_return_reversion_futures"

    def __init__(
        self,
        nk: int = 10,
        threshold: Decimal = Decimal("0.03"),
        take_profit_rate: Decimal = Decimal("0.018"),
        stop_loss_rate: Decimal = Decimal("0.033"),
        position_ratio: Decimal = Decimal("0.30"),
    ):
        super().__init__(trading_mode=TradingMode.FUTURE)
        self.nk = nk
        self.threshold = threshold
        self.take_profit_rate = take_profit_rate
        self.stop_loss_rate = stop_loss_rate
        self.position_ratio = position_ratio
        self.signals: list[int] = []

    def on_init(self) -> None:
        if self.data is None:
            return
        df = self.data.to_dataframe()
        df["close"] = df["close"].astype(float)
        df["log_return"] = np.log(df["close"] / df["close"].shift(1)).fillna(0)
        df["rolling_log_return"] = df["log_return"].rolling(window=self.nk).sum().fillna(0)
        threshold = float(self.threshold)
        df["reversion_signal"] = 0
        df.loc[df["rolling_log_return"] >= threshold, "reversion_signal"] = -1
        df.loc[df["rolling_log_return"] <= -threshold, "reversion_signal"] = 1
        self.signals = [int(value) for value in df["reversion_signal"].tolist()]

    def on_bar(self, bar: BarData) -> None:
        if self.data is None:
            return
        signal = self.signals[self.data.cursor] if self.data.cursor < len(self.signals) else 0

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

    strategy = RollingReturnReversionFuturesStrategy(
        nk=21,
        threshold=Decimal("0.07"),
        take_profit_rate=Decimal("0.018"),
        stop_loss_rate=Decimal("0.033"),
        position_ratio=Decimal("0.30"),
    )
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0"),
            leverage=Decimal("10"),
        )
    )
    result = engine.run(strategy, data)
    report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)
    BokehBacktestReport(
        result,
        data,
        title="Rolling Return Reversion Strategy Report",
    ).save("rolling_return_reversion_strategy_report.html")

    print("========== 滚动累计收益率反转策略 CSV 回测 ==========")
    print(result.final_account)
    print(report)
    print(f"orders: {len(result.orders)}")
    print(f"trades: {len(result.trades)}")


if __name__ == "__main__":
    main()