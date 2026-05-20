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
    params: dict[str, Any] = field(default_factory=dict) #这是额外参数，用来传给 ccxt / Binance，比如 Binance 某些特殊参数，框架没有单独设计字段，就可以放到 params 里。


'''
策略发出下单请求
    ↓
OrderRequest
    ↓
回测引擎撮合 / 实盘交易所撮合
    ↓
成交
    ↓
Trade
'''

@dataclass(slots=True)
class Trade:  #Trade 类表示一笔已经成交的交易记录，以后可以把 Trade 转成 TradeRecord 保存到 MySQL
    id: str #成交ID，在回测里，这个 ID 是框架自己用 uuid4() 生成的
    symbol: str #交易对名称
    side: OrderSide #交易方向，买入（BUY）或卖出（SELL）
    amount: Decimal #成交数量，表示这笔交易的数量（合约张数）
    price: Decimal #成交价格，表示这笔交易的价格
    fee: Decimal #成交费用，表示这笔交易产生的费用金额，手续费
    traded_at: datetime #在回测里，就是当前 K 线的时间，在实盘里，后续可以扩展为交易所真实返回的成交时间。


'''
策略发出下单意图
    ↓
OrderRequest：订单请求
    ↓
LocalOrder：框架本地订单，记录订单状态
    ↓
Trade：订单成交后生成成交记录

OrderRequest 只是“我要下单”的请求,这只是一个请求，还没有订单状态,但订单在生命周期中会有各种状态:
已提交
部分成交
全部成交
已撤销
已拒绝
已过期
所以框架需要一个对象来跟踪订单本身的状态，这就是 LocalOrder。
LocalOrder 包含了 OrderRequest 的信息，以及订单的状态、已成交数量、平均成交价格等信息。
当策略调用 self.buy() 或 self.sell() 等方法时，框架会生成一个 OrderRequest，然后根据是否绑定了引擎，
生成一个 LocalOrder（如果没有引擎）或者直接提交订单到引擎（如果有引擎）。无论哪种情况，LocalOrder 都会被用来跟踪订单的状态，
并在订单状态发生变化时调用策略的 on_order() 方法，让策略能够及时响应订单状态的变化。
'''
@dataclass(slots=True)
class LocalOrder: #LocalOrder 类表示策略发出的订单请求在框架内部的一个本地订单对象，它包含了订单请求的信息以及订单的状态和成交情况。
    id: str
    request: OrderRequest 
    status: OrderStatus = OrderStatus.OPEN #订单状态，默认为 OPEN（已提交），表示订单已经被创建但还没有被完全成交或取消.
    filled: Decimal = Decimal("0") #已成交数量，表示订单已经成交的数量（合约张数），初始值为 0。
    average: Decimal | None = None #平均成交价格，表示订单已经成交的平均价格，初始值为 None，表示还没有成交。
    created_at: datetime = field(default_factory=datetime.utcnow) #订单创建时间，默认为当前 UTC 时间，表示订单被创建的时间。
'''
项目里的状态枚举包括：
OrderStatus.OPEN       # open,订单打开，等待成交
OrderStatus.CLOSED     # closed,订单已完成成交
OrderStatus.CANCELED   # canceled,订单已撤销
OrderStatus.EXPIRED    # expired,订单过期
OrderStatus.REJECTED   # rejected,订单被拒绝，可能是因为资金不足、价格异常等原因导致交易所拒绝了订单请求
'''


'''
pass部分:
策略生命周期方法,默认都是pass,用户可以根据需要在自己的策略类里重写这些方法来实现自己的逻辑。
on_init()：策略初始化时调用，可以在这里设置一些初始参数或者状态。
on_start()：策略开始运行时调用，可以在这里执行一些启动时的操作，比如记录日志、发送通知等。
on_bar(bar: BarData)：每当有新的 K线数据到达时调用，参数 bar 是一个 BarData 对象，包含了当前 K线的数据，用户可以在这里实现自己的交易逻辑，比如根据 K 线数据计算技术指标、判断交易信号等。
on_trade(trade: Trade)：每当有新的成交记录生成时调用，参数 trade 是一个 Trade 对象，包含了成交的详细信息，用户可以在这里实现一些成交后的逻辑，比如更新持仓信息、计算盈亏、记录日志等。
on_order(order: LocalOrder)：每当有订单状态发生变化时调用，参数 order 是一个 LocalOrder 对象，包含了订单的详细信息和当前状态，用户可以在这里实现一些订单状态变化后的逻辑，比如根据订单状态更新账户信息、记录日志等。
on_stop()：策略停止运行时调用，可以在这里执行一些清理操作，比如关闭数据库连接、保存日志等。 

'''

class StrategyBase:
    name = "strategy_base"

    def __init__(self, trading_mode: TradingMode = TradingMode.SPOT): #记录当前的运行模式，默认是现货模式（SPOT）。这个参数会影响一些方法的行为，比如 close_position() 方法在期货模式下会使用 reduce_only 参数来确保只减仓不反向开仓。
        self.trading_mode = trading_mode
        self.account = Account(cash=Decimal("0"), equity=Decimal("0"), available=Decimal("0")) #账户信息，初始值为 0，在回测过程中会注入初始资金，然后根据策略的操作和市场数据不断更新这个账户信息。
        self.positions: dict[str, Position] = {} #持仓信息，使用一个字典来存储当前的持仓情况，键是由交易对名称和持仓方向组成的字符串（例如 "BTC/USDT:LONG"），值是 Position 对象，表示当前的持仓状态。
        self.orders: dict[str, LocalOrder] = {} #保存策略相关订单的字典，键是订单 ID，值是 LocalOrder 对象，表示当前策略发出的订单及其状态。
        self.trades: list[Trade] = [] #保存策略的成交记录，每次订单成交，回测引擎会生成 Trade，然后加入strategy.trades.append(trade)，这样策略就可以通过 self.trades 来访问所有的成交记录。
        self.data: DataFeed | None = None #保存当前策略绑定的数据源，在回测过程中，策略会被绑定到一个 DataFeed 对象上，这个对象提供了市场数据的访问接口，策略可以通过 self.data 来获取当前的 K 线数据、订单簿数据等。
        self.engine: Any = None #保存当前策略绑定的引擎，策略可以被绑定到一个回测引擎或实盘引擎上，这个引擎负责处理策略发出的订单请求、模拟成交（在回测中）或发送订单到交易所（在实盘中）。策略可以通过 self.engine 来访问这个引擎，并调用它的方法来提交订单、取消订单等。策略只负责产生交易意图，引擎负责执行交易意图

    def bind_engine(self, engine: Any) -> None: #把回测引擎或实盘引擎绑定到策略上，这样策略就可以通过 self.engine 来访问引擎，并调用它的方法来提交订单、取消订单等。策略只负责产生交易意图，引擎负责执行交易意图。
        self.engine = engine

    def bind_data(self, data: DataFeed) -> None: #把数据源绑定到策略上，这样策略就可以通过 self.data 来获取当前的 K 线数据、订单簿数据等。
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

    def get_position(self, symbol: str, side: PositionSide = PositionSide.BOTH) -> Position: #这个方法用于获取某个交易对的持仓信息，如果当前没有持仓，就返回一个 amount=0 的空仓对象。这个方法会根据交易对名称和持仓方向来生成一个键，然后在 self.positions 字典中查找对应的 Position 对象，如果没有找到，就创建一个新的 Position 对象并保存到字典中，最后返回这个 Position 对象。
        key = self._position_key(symbol, side)
        if key not in self.positions:
            self.positions[key] = Position(symbol=symbol, side=side)
        return self.positions[key]

    def buy(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str: #这是一个快捷方法，用于提交一个买入订单。它调用 submit_order() 方法，传入订单方向为 OrderSide.BUY，以及其他相关参数。这个方法返回订单 ID，策略可以通过这个 ID 来跟踪订单的状态。
        return self.submit_order(symbol, OrderSide.BUY, amount, price=price, **params)

    def sell(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str: #这是一个快捷方法，用于提交一个卖出订单。它调用 submit_order() 方法，传入订单方向为 OrderSide.SELL，以及其他相关参数。这个方法返回订单 ID，策略可以通过这个 ID 来跟踪订单的状态。
        return self.submit_order(symbol, OrderSide.SELL, amount, price=price, **params)

    def short(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str: #short() 是合约开空快捷方法，只有在期货模式下才有意义。它调用 submit_order() 方法，传入订单方向为 OrderSide.SELL，以及 position_side=PositionSide.SHORT 来表示这是一个开空订单。这个方法返回订单 ID，策略可以通过这个 ID 来跟踪订单的状态。
        return self.submit_order(
            symbol,
            OrderSide.SELL,
            amount,
            price=price,
            position_side=PositionSide.SHORT,
            **params,
        )

    def cover(self, symbol: str, amount: Decimal, price: Decimal | None = None, **params: Any) -> str: #买入 + position_side=SHORT + reduce_only=True，表示这是一个平空订单。这个方法返回订单 ID，策略可以通过这个 ID 来跟踪订单的状态。
        return self.submit_order(
            symbol,
            OrderSide.BUY,
            amount,
            price=price,
            position_side=PositionSide.SHORT,
            reduce_only=True,
            **params,
        )

    def submit_order( #核心下单方法 submit_order()，这是所有下单方法最终都会走的地方，是策略提交订单的核心方法，它接受订单的详细参数，生成一个 OrderRequest 对象，然后根据是否绑定了引擎来处理订单请求。如果没有绑定引擎，就创建一个 LocalOrder 对象，保存到 self.orders 字典中，并调用 on_order() 方法来通知策略有新的订单；如果绑定了引擎，就直接调用引擎的 submit_order() 方法来提交订单，并返回订单 ID。
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
    ) -> str: #它负责把一堆参数整理成 OrderRequest
        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=order_type or (OrderType.LIMIT if price is not None else OrderType.MARKET), #如果用户明确传了 order_type，就用用户传的；如果没传 order_type：如果传了 price，就默认是限价单；如果没传 price，就默认是市价单。
            amount=amount,
            price=price,
            position_side=position_side,
            reduce_only=reduce_only,
            time_in_force=time_in_force,
            params=params,
        )
        if self.engine is None: #如果策略还没有被回测引擎或实盘引擎绑定，就只在本地创建一张 LocalOrder。不会真正撮合成交，也不会发到交易所
            local_order = LocalOrder(id=str(uuid4()), request=request)
            self.orders[local_order.id] = local_order
            self.on_order(local_order)
            return local_order.id
        return self.engine.submit_order(self, request) #如果已经绑定引擎

    def cancel_order(self, order_id: str) -> None:
        if self.engine is not None: #如果绑定了引擎，就让引擎撤单。如果没有绑定引擎，就只改本地订单状态
            self.engine.cancel_order(self, order_id)
            return
        order = self.orders[order_id]
        order.status = OrderStatus.CANCELED
        self.on_order(order)

    def close_position(self, symbol: str, side: PositionSide = PositionSide.BOTH) -> str | None: #用于平掉当前持仓
        position = self.get_position(symbol, side)
        if position.is_flat: #如果本来就是空仓，什么都不做
            return None
        order_side = OrderSide.SELL if position.side != PositionSide.SHORT else OrderSide.BUY #判断平仓方向，如果不是空头仓位，平仓就是卖出；如果是空头仓位，平仓就是买入。
        return self.submit_order( #提交平仓单
            symbol=symbol,
            side=order_side,
            amount=abs(position.amount),
            position_side=side if self.trading_mode == TradingMode.FUTURE else None,
            reduce_only=self.trading_mode == TradingMode.FUTURE,
        )

    def _position_key(self, symbol: str, side: PositionSide) -> str: #这是一个内部辅助方法，这个方法主要供类内部使用，不建议外部直接调用。它把交易对和持仓方向拼成字典 key。
        return f"{symbol}:{side.value}"
