'''
dataclasses 是 Python 标准库，用于快速定义“数据域”的类，
Python 会自动生成 __init__、__repr__ 等方法，
slots=True 可以：减少对象内存占用；防止随便给对象添加不存在的字段；
让数据结构更稳定
'''

from dataclasses import dataclass, field  
from datetime import datetime
from decimal import Decimal  #Decimal 是 Python 标准库中的一个类，用于进行高精度的十进制浮点数运算，适用于金融计算等需要精确表示小数的场景。
from typing import Any #项目里和 ccxt 返回值相关的地方经常用 Any，因为交易所 API 返回结构复杂，不适合一开始就写得特别死
from uuid import uuid4 #uuid4() 是 Python 标准库 uuid 模块中的一个函数，用于生成一个随机的 UUID（Universally Unique Identifier，通用唯一识别码）。UUID 是一种 128 位长的数字，通常用来唯一标识信息，在分布式系统中非常有用。

from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, OrderType, PositionSide, TimeInForce, TradingMode


@dataclass(slots=True)
class Account: #账户信息类
    cash: Decimal  #现金余额
    equity: Decimal #账户权益
    available: Decimal #可用余额
    margin: Decimal = Decimal("0") #保证金
    realized_pnl: Decimal = Decimal("0") #已实现盈亏
    unrealized_pnl: Decimal = Decimal("0") #未实现盈亏


@dataclass(slots=True)
class Position: #持仓信息类
    symbol: str #交易对名称
    side: PositionSide #持仓方向，可能的值有 LONG、SHORT 和 BOTH
    amount: Decimal = Decimal("0") #合约张数
    entry_price: Decimal = Decimal("0") #开仓价格，表示当前持仓的平均开仓价格
    mark_price: Decimal = Decimal("0") #标记价格（当前市价），通常用于计算未实现盈亏和强平价格等
    unrealized_pnl: Decimal = Decimal("0") #未实现盈亏，表示当前持仓的潜在盈亏金额，计算公式通常是 (mark_price - entry_price) * amount，对于空头持仓则是 (entry_price - mark_price) * amount

    @property #@property 可以让一个方法像属性一样使用。在这个例子中，is_flat 方法被装饰为一个属性，这意味着你可以通过 position.is_flat 来访问它，而不需要加上括号 position.is_flat()。
    def is_flat(self) -> bool: #如果当前持仓数量 amount 等于 0，就认为这个仓位是空仓。
        return self.amount == 0
'''
订单请求类可以理解为：策略发出的“下单请求数据包”,它本身不负责真正下单，
只负责把一次下单需要的信息整理成一个对象，然后交给回测引擎或实盘引擎处理。
策略 self.buy()
    ↓
生成 OrderRequest
    ↓
回测引擎 / 实盘引擎
    ↓
模拟成交 / Binance 下单
'''

@dataclass(frozen=True, slots=True)
class OrderRequest: #订单请求类
    symbol: str #交易对名称
    side: OrderSide #订单方向
    order_type: OrderType #订单类型
    amount: Decimal #订单数量
    price: Decimal | None = None #订单价格,订单的类型可以是限价（Decimal ）类型的价格或者None（市价）
    position_side: PositionSide | None = None #持仓方向可以是 PositionSide 类型，也可以是 None，表示订单的持仓方向。对于现货交易，这个字段通常为 None，因为现货交易没有多空之分；对于期货交易，这个字段可以是 LONG、SHORT 或 BOTH，表示订单是开多仓、开空仓还是不区分方向。
    reduce_only: bool = False #是否只减仓，reduce_only=True，表示这个订单只能减少已有仓位，不能反向开新仓。
    time_in_force: TimeInForce | None = None #订单的有效时间，TimeInForce 是一个枚举类型，常见的值有 GTC（Good Till Canceled，直到取消）、IOC（Immediate Or Cancel，立即成交或取消）和 FOK（Fill Or Kill，全部成交或取消）。这个字段可以为 None，表示使用交易所默认的时间策略。
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
