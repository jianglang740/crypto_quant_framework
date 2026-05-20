from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from crypto_quant.config import BacktestConfig
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, PositionSide, TradingMode
from crypto_quant.strategy.base import Account, LocalOrder, OrderRequest, Position, StrategyBase, Trade

'''
运行示例：
输入：
    strategy: StrategyBase
    data: DataFeed

执行：
    绑定策略和数据
    设置初始账户
    调用 on_init()
    调用 on_start()
    for bar in data:
        当前 K 线 = bar
        按当前价格更新持仓浮盈浮亏
        调用 strategy.on_bar(bar)
        如果策略下单，就模拟成交
        记录权益曲线
    调用 on_stop()

输出：
    BacktestResult
可以画成：
DataFeed 一根一根吐出 BarData
        ↓
BacktestEngine.run()
        ↓
strategy.on_bar(bar)
        ↓
策略可能 self.buy()/self.sell()
        ↓
BacktestEngine.submit_order()
        ↓
BacktestEngine._fill_order()
        ↓
BacktestEngine._apply_trade()
        ↓
更新账户、持仓、成交、订单

'''

@dataclass(slots=True)
class BacktestResult:  #回测结果类
    trades: list[Trade] #成交纪录
    equity_curve: list[tuple[datetime, Decimal]] #权益曲线
    final_account: Account #回测结束后的最终账户状态
    orders: list[LocalOrder] = field(default_factory=list) #所有本地订单记录


class BacktestEngine: #回测引擎类
    def __init__(self, config: BacktestConfig | None = None): #如果你传了配置，就用你的配置，如果没传，就使用默认配置
        self.config = config or BacktestConfig() #如果你传了配置，就用你的配置，如果没传，就使用默认配置
        self.orders: dict[str, LocalOrder] = {} #保存所有订单的字典
        self.trades: list[Trade] = [] #保存所有成交纪录
        self.equity_curve: list[tuple[datetime, Decimal]] = [] #保存权益曲线
        self.current_bar: BarData | None = None #保存当前正在处理的k线

    def run(self, strategy: StrategyBase, data: DataFeed) -> BacktestResult: #输出指向BacktestResult
        strategy.bind_engine(self) #把当前回测引擎绑定到策略上
        strategy.bind_data(data) #把数据源绑定到策略上
        strategy.account = Account( #初始化账户
            cash=self.config.initial_cash,
            equity=self.config.initial_cash,
            available=self.config.initial_cash,
        )
        strategy.on_init() #调用策略初始化钩子
        strategy.on_start() #调用策略初始化钩子
        for bar in data: #这里会触发 DataFeed.__iter__()，也就是说，每循环一次，DataFeed 会推进 cursor，所有 DataLine 会同步 advance，yield 当前 BarData
            self.current_bar = bar #把当前 K 线保存到引擎，后面如果策略下单，_fill_order() 会用这个 bar 模拟成交
            self._mark_to_market(strategy, bar) #这个方法会根据当前 K 线收盘价，更新持仓的未实现盈亏和账户权益，即用当前 close 重新估算账户权益
            strategy.on_bar(bar) #调用策略逻辑
            self.equity_curve.append((bar.datetime, strategy.account.equity)) #标记每一时间点的对应权益
        strategy.on_stop() #回测结束，回测循环结束后调用
        return BacktestResult( #返回回测结束后的账户情况
            trades=self.trades,
            equity_curve=self.equity_curve,
            final_account=strategy.account,
            orders=list(self.orders.values()),
        )

    def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str: #接受来自策略i的订单
        order = LocalOrder(id=str(uuid4()), request=request) #创建本地订单，订单 ID 用 uuid4() 创建
        self.orders[order.id] = order #保存到引擎订单字典，引擎保存所有订单
        strategy.orders[order.id] = order #保存到策略订单字典，策略自己也保存一份订单引用，注意这是同一个 LocalOrder 对象，不是复制品，所以后面订单状态变化时，引擎和策略看到的是同一个对象
        strategy.on_order(order)
        self._fill_order(strategy, order) #撮合交易
        return order.id #创建订单ID，策略调用 buy() 或sell（）时最终会拿到这个订单 ID

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None: #撤单方法
        order = self.orders[order_id]
        if order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELED
            strategy.on_order(order)

    def _fill_order(self, strategy: StrategyBase, order: LocalOrder) -> None: #模拟交易所的撮合成交
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

    def _apply_trade( #更新账户和持仓，这个方法稍微复杂，是当前回测引擎里最需要认真读的地方
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> None:  #把一笔成交应用到账户和持仓上。
        side = position_side or PositionSide.BOTH #确定持仓方向
        position = strategy.get_position(trade.symbol, side) #获取持仓对象
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount #计算带方向的成交数量
        if strategy.trading_mode == TradingMode.FUTURE and side == PositionSide.SHORT: #合约空头特殊处理
            signed_amount = -signed_amount
        previous_amount = position.amount #旧持仓和新持仓
        new_amount = previous_amount + signed_amount #旧持仓和新持仓
        notional = trade.price * trade.amount #成交额
        if reduce_only: #如果订单是只减仓，说明它是平仓性质的订单，这时计算已实现盈亏，例如合约平空、平多，或者显式 reduce_only 的订单
            strategy.account.realized_pnl += self._realized_pnl(position, trade)
        elif previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0): #如果是加仓或开仓
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
        else: #如果是减仓或反手
            strategy.account.realized_pnl += self._realized_pnl(position, trade)
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                position.entry_price = trade.price
        position.amount = new_amount
        position.mark_price = trade.price
        strategy.account.cash -= notional + trade.fee if trade.side == OrderSide.BUY else -notional + trade.fee
        strategy.account.available = strategy.account.cash

    def _realized_pnl(self, position: Position, trade: Trade) -> Decimal: #计算已实现盈亏
        if position.side == PositionSide.SHORT: #空头盈亏
            return (position.entry_price - trade.price) * trade.amount - trade.fee
        return (trade.price - position.entry_price) * trade.amount - trade.fee #多头盈亏

    def _mark_to_market(self, strategy: StrategyBase, bar: BarData) -> None: #盯市更新权益，这个方法用于根据当前 K 线价格更新账户权益
        unrealized = Decimal("0") #初始化所有持仓未实现盈亏总和
        position_value = Decimal("0") #初始化现货/多头持仓当前市值
        for position in strategy.positions.values(): #遍历所有持仓，策略可能有多个交易对或多个方向持仓
            position.mark_price = bar.close #当前版本用当前 K 线 close 作为标记价格
            if position.amount == 0: #如果没有持仓，未实现盈亏为 0
                position.unrealized_pnl = Decimal("0")
                continue
            if position.side == PositionSide.SHORT: # 空头未实现盈亏
                position.unrealized_pnl = (position.entry_price - bar.close) * abs(position.amount)
            else: #多头/现货未实现盈亏
                position.unrealized_pnl = (bar.close - position.entry_price) * position.amount
                position_value += bar.close * position.amount
            unrealized += position.unrealized_pnl #汇总未实现盈亏
        strategy.account.unrealized_pnl = unrealized #更新账户
        strategy.account.equity = strategy.account.cash + position_value + unrealized #更新账户
