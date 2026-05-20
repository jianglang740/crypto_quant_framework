from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, OrderType, PositionSide, TimeInForce, TradingMode


@dataclass(slots=True)
class Account:
    cash: Decimal
    equity: Decimal
    available: Decimal
    margin: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")


@dataclass(slots=True)
class Position:
    symbol: str
    side: PositionSide
    amount: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    mark_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")

    @property
    def is_flat(self) -> bool:
        return self.amount == 0


@dataclass(frozen=True, slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: Decimal
    price: Decimal | None = None
    position_side: PositionSide | None = None
    reduce_only: bool = False
    time_in_force: TimeInForce | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Trade:
    id: str
    symbol: str
    side: OrderSide
    amount: Decimal
    price: Decimal
    fee: Decimal
    traded_at: datetime


@dataclass(slots=True)
class LocalOrder:
    id: str
    request: OrderRequest
    status: OrderStatus = OrderStatus.OPEN
    filled: Decimal = Decimal("0")
    average: Decimal | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class StrategyBase:
    name = "strategy_base"

    def __init__(self, trading_mode: TradingMode = TradingMode.SPOT):
        self.trading_mode = trading_mode
        self.account = Account(cash=Decimal("0"), equity=Decimal("0"), available=Decimal("0"))
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, LocalOrder] = {}
        self.trades: list[Trade] = []
        self.data: DataFeed | None = None
        self.engine: Any = None

    def bind_engine(self, engine: Any) -> None:
        self.engine = engine

    def bind_data(self, data: DataFeed) -> None:
        self.data = data

    def on_init(self) -> None:
        pass

    def on_start(self) -> None:
        pass

    def on_bar(self, bar: BarData) -> None:
        pass

    def on_trade(self, trade: Trade) -> None:
        pass

    def on_order(self, order: LocalOrder) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def get_position(self, symbol: str, side: PositionSide = PositionSide.BOTH) -> Position:
        key = self._position_key(symbol, side)
        if key not in self.positions:
            self.positions[key] = Position(symbol=symbol, side=side)
        return self.positions[key]

    def buy(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str:
        return self.submit_order(symbol, OrderSide.BUY, amount, price=price, **params)

    def sell(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str:
        return self.submit_order(symbol, OrderSide.SELL, amount, price=price, **params)

    def short(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str:
        return self.submit_order(
            symbol,
            OrderSide.SELL,
            amount,
            price=price,
            position_side=PositionSide.SHORT,
            **params,
        )

    def cover(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str:
        return self.submit_order(
            symbol,
            OrderSide.BUY,
            amount,
            price=price,
            position_side=PositionSide.SHORT,
            reduce_only=True,
            **params,
        )

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: Decimal,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        position_side: PositionSide | None = None,
        reduce_only: bool = False,
        time_in_force: TimeInForce | None = None,
        **params: Any,
    ) -> str:
        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=order_type or (OrderType.LIMIT if price is not None else OrderType.MARKET),
            amount=amount,
            price=price,
            position_side=position_side,
            reduce_only=reduce_only,
            time_in_force=time_in_force,
            params=params,
        )
        if self.engine is None:
            local_order = LocalOrder(id=str(uuid4()), request=request)
            self.orders[local_order.id] = local_order
            self.on_order(local_order)
            return local_order.id
        return self.engine.submit_order(self, request)

    def cancel_order(self, order_id: str) -> None:
        if self.engine is not None:
            self.engine.cancel_order(self, order_id)
            return
        order = self.orders[order_id]
        order.status = OrderStatus.CANCELED
        self.on_order(order)

    def close_position(self, symbol: str, side: PositionSide = PositionSide.BOTH) -> str | None:
        position = self.get_position(symbol, side)
        if position.is_flat:
            return None
        order_side = OrderSide.SELL if position.side != PositionSide.SHORT else OrderSide.BUY
        return self.submit_order(
            symbol=symbol,
            side=order_side,
            amount=abs(position.amount),
            position_side=side if self.trading_mode == TradingMode.FUTURE else None,
            reduce_only=self.trading_mode == TradingMode.FUTURE,
        )

    def _position_key(self, symbol: str, side: PositionSide) -> str:
        return f"{symbol}:{side.value}"
