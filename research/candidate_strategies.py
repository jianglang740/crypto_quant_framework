from __future__ import annotations

from collections import deque
from decimal import Decimal

from crypto_quant.data.feed import BarData
from crypto_quant.enums import PositionSide, TradingMode
from crypto_quant.strategy.base import StrategyBase


class ResearchVolatilitySqueezeBreakoutStrategy(StrategyBase):
    name = "research_volatility_squeeze_breakout"

    def __init__(
        self,
        breakout_window: int = 36,
        range_window: int = 12,
        compression_ratio: Decimal = Decimal("0.65"),
        breakout_buffer: Decimal = Decimal("0.001"),
        volume_window: int = 24,
        volume_multiplier: Decimal = Decimal("1.2"),
        position_ratio: Decimal = Decimal("0.08"),
        stop_loss_rate: Decimal = Decimal("0.01"),
        take_profit_rate: Decimal = Decimal("0.018"),
        max_bars_in_position: int = 36,
        cooldown_bars: int = 6,
        trading_mode: TradingMode = TradingMode.FUTURE,
    ) -> None:
        super().__init__(trading_mode=trading_mode)
        self.breakout_window = breakout_window
        self.range_window = range_window
        self.compression_ratio = compression_ratio
        self.breakout_buffer = breakout_buffer
        self.volume_window = volume_window
        self.volume_multiplier = volume_multiplier
        self.position_ratio = position_ratio
        self.stop_loss_rate = stop_loss_rate
        self.take_profit_rate = take_profit_rate
        self.max_bars_in_position = max_bars_in_position
        self.cooldown_bars = cooldown_bars
        self.bars: deque[BarData] = deque(maxlen=max(breakout_window, range_window * 2, volume_window) + 1)
        self.bars_in_position = 0
        self.cooldown_left = 0

    def on_bar(self, bar: BarData) -> None:
        position = self.get_position(bar.symbol, PositionSide.BOTH)
        if not position.is_flat:
            self.bars_in_position += 1
            if self._should_exit(position.entry_price, bar.close):
                self.close_position(bar.symbol)
                self.bars_in_position = 0
                self.cooldown_left = self.cooldown_bars
            self.bars.append(bar)
            return

        if self.cooldown_left > 0:
            self.cooldown_left -= 1
            self.bars.append(bar)
            return

        previous_bars = list(self.bars)
        if len(previous_bars) >= max(self.breakout_window, self.range_window * 2, self.volume_window):
            prior_high = max(item.high for item in previous_bars[-self.breakout_window :])
            recent_range = self._average_range(previous_bars[-self.range_window :])
            prior_range = self._average_range(previous_bars[-self.range_window * 2 : -self.range_window])
            average_volume = sum(item.volume for item in previous_bars[-self.volume_window :]) / Decimal(self.volume_window)
            squeezed = prior_range > 0 and recent_range <= prior_range * self.compression_ratio
            breakout = bar.close > prior_high * (Decimal("1") + self.breakout_buffer)
            volume_confirmed = average_volume > 0 and bar.volume >= average_volume * self.volume_multiplier
            if squeezed and breakout and volume_confirmed:
                amount = self._order_amount(bar.close)
                if amount > 0:
                    self.buy(bar.symbol, amount)
                    self.bars_in_position = 0

        self.bars.append(bar)

    def _average_range(self, bars: list[BarData]) -> Decimal:
        return sum((item.high - item.low) / item.close for item in bars if item.close > 0) / Decimal(len(bars))

    def _should_exit(self, entry_price: Decimal, close: Decimal) -> bool:
        if entry_price <= 0:
            return False
        if close <= entry_price * (Decimal("1") - self.stop_loss_rate):
            return True
        if close >= entry_price * (Decimal("1") + self.take_profit_rate):
            return True
        return self.bars_in_position >= self.max_bars_in_position

    def _order_amount(self, price: Decimal) -> Decimal:
        if price <= 0 or self.account.equity <= 0:
            return Decimal("0")
        return (self.account.equity * self.position_ratio) / price


class ResearchLiquiditySweepReclaimStrategy(StrategyBase):
    name = "research_liquidity_sweep_reclaim"

    def __init__(
        self,
        sweep_window: int = 48,
        sweep_buffer: Decimal = Decimal("0.001"),
        reclaim_buffer: Decimal = Decimal("0.0005"),
        min_lower_wick_ratio: Decimal = Decimal("0.45"),
        volume_window: int = 24,
        volume_multiplier: Decimal = Decimal("1.1"),
        position_ratio: Decimal = Decimal("0.08"),
        stop_loss_rate: Decimal = Decimal("0.008"),
        take_profit_rate: Decimal = Decimal("0.012"),
        max_bars_in_position: int = 24,
        cooldown_bars: int = 6,
        trading_mode: TradingMode = TradingMode.FUTURE,
    ) -> None:
        super().__init__(trading_mode=trading_mode)
        self.sweep_window = sweep_window
        self.sweep_buffer = sweep_buffer
        self.reclaim_buffer = reclaim_buffer
        self.min_lower_wick_ratio = min_lower_wick_ratio
        self.volume_window = volume_window
        self.volume_multiplier = volume_multiplier
        self.position_ratio = position_ratio
        self.stop_loss_rate = stop_loss_rate
        self.take_profit_rate = take_profit_rate
        self.max_bars_in_position = max_bars_in_position
        self.cooldown_bars = cooldown_bars
        self.bars: deque[BarData] = deque(maxlen=max(sweep_window, volume_window) + 1)
        self.bars_in_position = 0
        self.cooldown_left = 0

    def on_bar(self, bar: BarData) -> None:
        position = self.get_position(bar.symbol, PositionSide.BOTH)
        if not position.is_flat:
            self.bars_in_position += 1
            if self._should_exit(position.entry_price, bar.close):
                self.close_position(bar.symbol)
                self.bars_in_position = 0
                self.cooldown_left = self.cooldown_bars
            self.bars.append(bar)
            return

        if self.cooldown_left > 0:
            self.cooldown_left -= 1
            self.bars.append(bar)
            return

        previous_bars = list(self.bars)
        if len(previous_bars) >= max(self.sweep_window, self.volume_window):
            prior_low = min(item.low for item in previous_bars[-self.sweep_window :])
            average_volume = sum(item.volume for item in previous_bars[-self.volume_window :]) / Decimal(self.volume_window)
            swept_low = bar.low < prior_low * (Decimal("1") - self.sweep_buffer)
            reclaimed = bar.close > prior_low * (Decimal("1") + self.reclaim_buffer)
            wick_confirmed = self._lower_wick_ratio(bar) >= self.min_lower_wick_ratio
            volume_confirmed = average_volume > 0 and bar.volume >= average_volume * self.volume_multiplier
            if swept_low and reclaimed and wick_confirmed and volume_confirmed:
                amount = self._order_amount(bar.close)
                if amount > 0:
                    self.buy(bar.symbol, amount)
                    self.bars_in_position = 0

        self.bars.append(bar)

    def _lower_wick_ratio(self, bar: BarData) -> Decimal:
        candle_range = bar.high - bar.low
        if candle_range <= 0:
            return Decimal("0")
        lower_body = min(bar.open, bar.close)
        return (lower_body - bar.low) / candle_range

    def _should_exit(self, entry_price: Decimal, close: Decimal) -> bool:
        if entry_price <= 0:
            return False
        if close <= entry_price * (Decimal("1") - self.stop_loss_rate):
            return True
        if close >= entry_price * (Decimal("1") + self.take_profit_rate):
            return True
        return self.bars_in_position >= self.max_bars_in_position

    def _order_amount(self, price: Decimal) -> Decimal:
        if price <= 0 or self.account.equity <= 0:
            return Decimal("0")
        return (self.account.equity * self.position_ratio) / price
