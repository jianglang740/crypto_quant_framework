from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from crypto_quant.config import BacktestConfig
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, PositionSide, TradingMode
from crypto_quant.strategy.base import Account, LocalOrder, OrderRequest, Position, StrategyBase, Trade


@dataclass(slots=True)
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[tuple[datetime, Decimal]]
    final_account: Account
    orders: list[LocalOrder] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.orders: dict[str, LocalOrder] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        self.current_bar: BarData | None = None

    def run(self, strategy: StrategyBase, data: DataFeed) -> BacktestResult:
        strategy.bind_engine(self)
        strategy.bind_data(data)
        strategy.account = Account(
            cash=self.config.initial_cash,
            equity=self.config.initial_cash,
            available=self.config.initial_cash,
        )
        strategy.on_init()
        strategy.on_start()
        for bar in data:
            self.current_bar = bar
            self._mark_to_market(strategy, bar)
            strategy.on_bar(bar)
            self.equity_curve.append((bar.datetime, strategy.account.equity))
        strategy.on_stop()
        return BacktestResult(
            trades=self.trades,
            equity_curve=self.equity_curve,
            final_account=strategy.account,
            orders=list(self.orders.values()),
        )

    def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        order = LocalOrder(id=str(uuid4()), request=request)
        self.orders[order.id] = order
        strategy.orders[order.id] = order
        strategy.on_order(order)
        self._fill_order(strategy, order)
        return order.id

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None:
        order = self.orders[order_id]
        if order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELED
            strategy.on_order(order)

    def _fill_order(self, strategy: StrategyBase, order: LocalOrder) -> None:
        if self.current_bar is None:
            return
        request = order.request
        fill_price = request.price or self.current_bar.close
        if request.price is not None:
            if request.side == OrderSide.BUY and request.price < self.current_bar.low:
                return
            if request.side == OrderSide.SELL and request.price > self.current_bar.high:
                return
        slippage = fill_price * self.config.slippage_rate
        fill_price = fill_price + slippage if request.side == OrderSide.BUY else fill_price - slippage
        notional = fill_price * request.amount
        fee = notional * self.config.commission_rate
        trade = Trade(
            id=str(uuid4()),
            symbol=request.symbol,
            side=request.side,
            amount=request.amount,
            price=fill_price,
            fee=fee,
            traded_at=self.current_bar.datetime,
        )
        self._apply_trade(strategy, trade, request.position_side, request.reduce_only)
        order.filled = request.amount
        order.average = fill_price
        order.status = OrderStatus.CLOSED
        self.trades.append(trade)
        strategy.trades.append(trade)
        strategy.on_trade(trade)
        strategy.on_order(order)

    def _apply_trade(
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> None:
        side = position_side or PositionSide.BOTH
        position = strategy.get_position(trade.symbol, side)
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
        if strategy.trading_mode == TradingMode.FUTURE and side == PositionSide.SHORT:
            signed_amount = -signed_amount
        previous_amount = position.amount
        new_amount = previous_amount + signed_amount
        notional = trade.price * trade.amount
        if reduce_only:
            strategy.account.realized_pnl += self._realized_pnl(position, trade)
        elif previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0):
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
        else:
            strategy.account.realized_pnl += self._realized_pnl(position, trade)
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                position.entry_price = trade.price
        position.amount = new_amount
        position.mark_price = trade.price
        strategy.account.cash -= notional + trade.fee if trade.side == OrderSide.BUY else -notional + trade.fee
        strategy.account.available = strategy.account.cash

    def _realized_pnl(self, position: Position, trade: Trade) -> Decimal:
        if position.side == PositionSide.SHORT:
            return (position.entry_price - trade.price) * trade.amount - trade.fee
        return (trade.price - position.entry_price) * trade.amount - trade.fee

    def _mark_to_market(self, strategy: StrategyBase, bar: BarData) -> None:
        unrealized = Decimal("0")
        position_value = Decimal("0")
        for position in strategy.positions.values():
            position.mark_price = bar.close
            if position.amount == 0:
                position.unrealized_pnl = Decimal("0")
                continue
            if position.side == PositionSide.SHORT:
                position.unrealized_pnl = (position.entry_price - bar.close) * abs(position.amount)
            else:
                position.unrealized_pnl = (bar.close - position.entry_price) * position.amount
                position_value += bar.close * position.amount
            unrealized += position.unrealized_pnl
        strategy.account.unrealized_pnl = unrealized
        strategy.account.equity = strategy.account.cash + position_value + unrealized
