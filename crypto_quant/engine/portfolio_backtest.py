from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from crypto_quant.config import BacktestConfig
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, PositionSide, TradingMode
from crypto_quant.strategy.base import Account, LocalOrder, OrderRequest, Position, StrategyBase, Trade


@dataclass(slots=True)
class PortfolioBacktestResult:
    trades: list[Trade]
    equity_curve: list[tuple[datetime, Decimal]]
    final_account: Account
    orders: list[LocalOrder] = field(default_factory=list)
    strategy_orders: dict[str, list[LocalOrder]] = field(default_factory=dict)
    strategy_trades: dict[str, list[Trade]] = field(default_factory=dict)


class PortfolioBacktestEngine:
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.account = Account(
            cash=self.config.initial_cash,
            equity=self.config.initial_cash,
            available=self.config.initial_cash,
        )
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, LocalOrder] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        self.current_bar: BarData | None = None
        self.order_strategy: dict[str, StrategyBase] = {}
        self.strategy_orders: dict[str, list[LocalOrder]] = {}
        self.strategy_trades: dict[str, list[Trade]] = {}
        self.trading_mode = TradingMode.SPOT

    def run(self, strategies: list[StrategyBase], data: DataFeed) -> PortfolioBacktestResult:
        if not strategies:
            raise ValueError("strategies cannot be empty")
        self._reset(strategies)
        for strategy in strategies:
            strategy.bind_engine(self)
            strategy.bind_data(data)
            strategy.account = self.account
            strategy.positions = self.positions
            strategy.orders = {}
            strategy.trades = []
            self.strategy_orders[strategy.name] = []
            self.strategy_trades[strategy.name] = []
            strategy.on_init()
        for strategy in strategies:
            strategy.on_start()
        for bar in data:
            self.current_bar = bar
            self._mark_to_market(bar)
            self._fill_open_orders()
            if self._check_liquidation(bar):
                self.equity_curve.append((bar.datetime, self.account.equity))
                break
            for strategy in strategies:
                strategy.on_bar(bar)
            self._mark_to_market(bar)
            self.equity_curve.append((bar.datetime, self.account.equity))
        for strategy in strategies:
            strategy.on_stop()
        if self.current_bar is not None and self.equity_curve:
            self._mark_to_market(self.current_bar)
            self.equity_curve[-1] = (self.current_bar.datetime, self.account.equity)
        return PortfolioBacktestResult(
            trades=self.trades,
            equity_curve=self.equity_curve,
            final_account=self.account,
            orders=list(self.orders.values()),
            strategy_orders=self.strategy_orders,
            strategy_trades=self.strategy_trades,
        )

    def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        order = LocalOrder(id=str(uuid4()), request=request)
        self.orders[order.id] = order
        strategy.orders[order.id] = order
        self.order_strategy[order.id] = strategy
        self.strategy_orders.setdefault(strategy.name, []).append(order)
        strategy.on_order(order)
        # 新订单延迟到下一根 K 线撮合，避免收盘出信号后又在同一根 K 线成交。
        return order.id

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None:
        order = self.orders[order_id]
        if order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELED
            self.order_strategy[order_id].on_order(order)

    def _reset(self, strategies: list[StrategyBase]) -> None:
        trading_modes = {strategy.trading_mode for strategy in strategies}
        if len(trading_modes) != 1:
            raise ValueError("portfolio backtest requires strategies to use the same trading_mode")
        self.trading_mode = trading_modes.pop()
        self.account = Account(
            cash=self.config.initial_cash,
            equity=self.config.initial_cash,
            available=self.config.initial_cash,
        )
        self.positions = {}
        self.orders = {}
        self.trades = []
        self.equity_curve = []
        self.current_bar = None
        self.order_strategy = {}
        self.strategy_orders = {}
        self.strategy_trades = {}

    def _fill_open_orders(self) -> None:
        for order in list(self.orders.values()):
            if order.status == OrderStatus.OPEN:
                self._fill_order(order)

    def _fill_order(self, order: LocalOrder) -> None:
        if self.current_bar is None:
            return
        request = order.request
        # 市价单采用“收盘出信号，次根开盘成交”的回测假设。
        fill_price = request.price or self.current_bar.open
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
        filled = self._apply_trade(trade, request.position_side, request.reduce_only)
        strategy = self.order_strategy[order.id]
        if not filled:
            order.status = OrderStatus.REJECTED
            strategy.on_order(order)
            return
        order.filled = request.amount
        order.average = fill_price
        order.status = OrderStatus.CLOSED
        self.trades.append(trade)
        strategy.trades.append(trade)
        self.strategy_trades.setdefault(strategy.name, []).append(trade)
        strategy.on_trade(trade)
        strategy.on_order(order)

    def _apply_trade(
        self,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        if self.trading_mode == TradingMode.FUTURE:
            return self._apply_futures_trade(trade, position_side, reduce_only)
        return self._apply_spot_trade(trade, position_side, reduce_only)

    def _apply_spot_trade(
        self,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        side = position_side or PositionSide.BOTH
        position = self._get_position(trade.symbol, side)
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
        previous_amount = position.amount
        new_amount = previous_amount + signed_amount
        if not self.config.allow_short and new_amount < 0:
            return False
        if reduce_only and abs(signed_amount) > abs(previous_amount):
            return False
        notional = trade.price * trade.amount
        cash_change = -(notional + trade.fee) if trade.side == OrderSide.BUY else notional - trade.fee
        if self.account.cash + cash_change < 0:
            return False
        if reduce_only:
            self.account.realized_pnl += self._realized_pnl(position, trade)
        elif previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0):
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
        else:
            self.account.realized_pnl += self._realized_pnl(position, trade)
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                position.entry_price = trade.price
        position.amount = new_amount
        position.mark_price = trade.price
        self.account.cash += cash_change
        self.account.available = self.account.cash
        return True

    def _apply_futures_trade(
        self,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        side = position_side or PositionSide.BOTH
        position = self._get_position(trade.symbol, side)
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
        if side == PositionSide.SHORT:
            signed_amount = -signed_amount
        previous_amount = position.amount
        new_amount = previous_amount + signed_amount
        if not self.config.allow_short and (side == PositionSide.SHORT or new_amount < 0):
            return False
        if reduce_only and (previous_amount == 0 or abs(signed_amount) > abs(previous_amount)):
            return False
        if previous_amount != 0 and (previous_amount > 0) != (signed_amount > 0) and abs(signed_amount) > abs(previous_amount):
            return False

        notional = trade.price * trade.amount
        leverage = self.config.leverage if self.config.leverage > 0 else Decimal("1")
        is_opening = previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0)
        if is_opening and not reduce_only:
            required_margin = notional / leverage
            if self.account.available < required_margin + trade.fee:
                return False
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
            position.margin += required_margin
            self.account.margin += required_margin
            self.account.cash -= trade.fee
        else:
            close_amount = min(abs(trade.amount), abs(previous_amount))
            close_ratio = close_amount / abs(previous_amount)
            released_margin = position.margin * close_ratio
            realized_pnl = self._realized_pnl(position, trade)
            self.account.realized_pnl += realized_pnl
            self.account.cash += realized_pnl
            position.margin -= released_margin
            self.account.margin -= released_margin
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                opened_amount = abs(signed_amount) - abs(previous_amount)
                opened_notional = trade.price * opened_amount
                required_margin = opened_notional / leverage
                if self.account.available < required_margin:
                    return False
                position.entry_price = trade.price
                position.margin += required_margin
                self.account.margin += required_margin
            elif new_amount == 0:
                position.entry_price = Decimal("0")
                position.margin = Decimal("0")
        position.amount = new_amount
        position.mark_price = trade.price
        if self.current_bar is not None:
            self._mark_to_market(self.current_bar)
        return True

    def _get_position(self, symbol: str, side: PositionSide = PositionSide.BOTH) -> Position:
        key = f"{symbol}:{side.value}"
        if key not in self.positions:
            self.positions[key] = Position(symbol=symbol, side=side)
        return self.positions[key]

    def _realized_pnl(self, position: Position, trade: Trade) -> Decimal:
        if position.side == PositionSide.SHORT:
            return (position.entry_price - trade.price) * trade.amount - trade.fee
        return (trade.price - position.entry_price) * trade.amount - trade.fee

    def _check_liquidation(self, bar: BarData) -> bool:
        if self.trading_mode != TradingMode.FUTURE:
            return False
        if self.account.margin <= 0:
            return False
        if self.account.equity <= self.account.maintenance_margin:
            self._liquidate_all(bar)
            return True
        return False

    def _liquidate_all(self, bar: BarData) -> None:
        for position in self.positions.values():
            if position.amount == 0:
                continue
            side = OrderSide.BUY if position.side == PositionSide.SHORT else OrderSide.SELL
            amount = abs(position.amount)
            notional = bar.close * amount
            fee = notional * self.config.liquidation_fee_rate
            trade = Trade(
                id=str(uuid4()),
                symbol=position.symbol,
                side=side,
                amount=amount,
                price=bar.close,
                fee=fee,
                traded_at=bar.datetime,
            )
            realized_pnl = self._realized_pnl(position, trade)
            self.account.realized_pnl += realized_pnl
            self.account.cash += realized_pnl
            self.account.margin -= position.margin
            position.amount = Decimal("0")
            position.entry_price = Decimal("0")
            position.mark_price = bar.close
            position.margin = Decimal("0")
            position.liquidation_price = None
            position.unrealized_pnl = Decimal("0")
            self.trades.append(trade)
            for strategy in self.strategy_trades:
                self.strategy_trades[strategy].append(trade)
        self.account.margin = Decimal("0")
        self.account.maintenance_margin = Decimal("0")
        self.account.margin_ratio = Decimal("0")
        self.account.unrealized_pnl = Decimal("0")
        self.account.cash = max(self.account.cash, Decimal("0"))
        self.account.equity = self.account.cash
        self.account.available = self.account.equity

    def _liquidation_price(self, position: Position) -> Decimal | None:
        if position.amount == 0 or position.entry_price == 0:
            return None
        leverage = self.config.leverage if self.config.leverage > 0 else Decimal("1")
        if position.side == PositionSide.SHORT:
            return position.entry_price * (Decimal("1") + Decimal("1") / leverage - self.config.maintenance_margin_rate)
        return position.entry_price * (Decimal("1") - Decimal("1") / leverage + self.config.maintenance_margin_rate)

    def _mark_to_market(self, bar: BarData) -> None:
        unrealized = Decimal("0")
        position_value = Decimal("0")
        maintenance_margin = Decimal("0")
        for position in self.positions.values():
            position.mark_price = bar.close
            if position.amount == 0:
                position.unrealized_pnl = Decimal("0")
                continue
            if position.side == PositionSide.SHORT:
                position.unrealized_pnl = (position.entry_price - bar.close) * abs(position.amount)
            else:
                position.unrealized_pnl = (bar.close - position.entry_price) * position.amount
                position_value += bar.close * position.amount
            if self.trading_mode == TradingMode.FUTURE:
                maintenance_margin += bar.close * abs(position.amount) * self.config.maintenance_margin_rate
                position.liquidation_price = self._liquidation_price(position)
            unrealized += position.unrealized_pnl
        self.account.unrealized_pnl = unrealized
        if self.trading_mode == TradingMode.FUTURE:
            self.account.maintenance_margin = maintenance_margin
            self.account.equity = self.account.cash + unrealized
            self.account.available = self.account.equity - self.account.margin
            if maintenance_margin == 0:
                self.account.margin_ratio = Decimal("0")
            else:
                self.account.margin_ratio = maintenance_margin / self.account.equity if self.account.equity > 0 else Decimal("Infinity")
        else:
            self.account.maintenance_margin = Decimal("0")
            self.account.margin_ratio = Decimal("0")
            self.account.equity = self.account.cash + position_value
            self.account.available = self.account.cash