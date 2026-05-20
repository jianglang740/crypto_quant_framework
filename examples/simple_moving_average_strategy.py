from collections import deque
from decimal import Decimal

from crypto_quant.data.feed import BarData
from crypto_quant.enums import PositionSide, TradingMode
from crypto_quant.strategy.base import StrategyBase


class SimpleMovingAverageStrategy(StrategyBase):
    name = "simple_moving_average"

    def __init__(self, fast_window: int = 5, slow_window: int = 20, trading_mode: TradingMode = TradingMode.SPOT):
        super().__init__(trading_mode=trading_mode)
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.closes: deque[Decimal] = deque(maxlen=slow_window)

    def on_bar(self, bar: BarData) -> None:
        self.closes.append(bar.close)
        if len(self.closes) < self.slow_window:
            return
        fast_ma = sum(list(self.closes)[-self.fast_window:]) / Decimal(self.fast_window)
        slow_ma = sum(self.closes) / Decimal(self.slow_window)
        position = self.get_position(bar.symbol, PositionSide.BOTH)
        if fast_ma > slow_ma and position.is_flat:
            self.buy(bar.symbol, Decimal("0.01"))
        elif fast_ma < slow_ma and not position.is_flat:
            self.close_position(bar.symbol)
