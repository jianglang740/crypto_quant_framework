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
    equity_curve: list[tuple[datetime, Decimal]] #权益曲线，列表里是元组，每个元素是 (时间, 权益)
    final_account: Account #回测结束后的最终账户状态
    orders: list[LocalOrder] = field(default_factory=list) #所有本地订单记录，field(default_factory=list)表示每次创建BacktestResult时，都创建一个新的空列表


class BacktestEngine: #回测引擎类
    def __init__(self, config: BacktestConfig | None = None): #如果你传了配置，就用你的配置，如果没传，就使用默认配置
        self.config = config or BacktestConfig() #如果你传了配置，就用你的配置，如果没传，就使用默认配置
        self.orders: dict[str, LocalOrder] = {} #保存所有订单的字典，注意是保存回测过程中所有订单
        self.trades: list[Trade] = [] #保存回测过程中的所有成交纪录
        self.equity_curve: list[tuple[datetime, Decimal]] = [] #保存权益曲线
        self.current_bar: BarData | None = None #保存当前正在处理的k线，用于撮合订单

    def run(self, strategy: StrategyBase, data: DataFeed) -> BacktestResult: #输出指向BacktestResult，即回测结果
        self.orders = {}
        self.trades = []
        self.equity_curve = []
        self.current_bar = None
        strategy.orders = {}
        strategy.trades = []
        strategy.positions = {}
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
            self.current_bar = bar #把当前 K 线保存到引擎，后面如果策略下单，_fill_order() 会用这个 bar的下一根bar的开盘价来模拟成交
            self._mark_to_market(strategy, bar) #这个方法会根据当前 K 线收盘价，更新持仓的未实现盈亏和账户权益，即用当前 close 重新估算账户权益
            self._fill_open_orders(strategy)
            if self._check_liquidation(strategy, bar): #强平检查
                self.equity_curve.append((bar.datetime, strategy.account.equity)) #标记每一时间点的对应权益，用来更新权益曲线
                break
            strategy.on_bar(bar) #调用策略逻辑
            self.equity_curve.append((bar.datetime, strategy.account.equity)) #标记每一时间点的对应权益，用来更新权益曲线
        strategy.on_stop() #回测结束，回测循环结束后调用
        if self.current_bar is not None and self.equity_curve:
            self._mark_to_market(strategy, self.current_bar)
            self.equity_curve[-1] = (self.current_bar.datetime, strategy.account.equity) #用回测结束时的最后一根k线来估计权益
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
        # 新订单延迟到下一根 K 线撮合，避免收盘出信号后又在同一根 K 线成交的未来函数问题。
        return order.id #创建订单ID，策略调用 buy() 或sell（）时最终会拿到这个订单 ID

    def _fill_open_orders(self, strategy: StrategyBase) -> None: #订单撮合前的检查
        for order in list(self.orders.values()): #遍历订单表
            if order.status == OrderStatus.OPEN: #找到处于open状态的订单
                self._fill_order(strategy, order)

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None: #撤单方法
        order = self.orders[order_id]
        if order.status == OrderStatus.OPEN: #找到处于open状态的订单
            order.status = OrderStatus.CANCELED #然后撤销它
            strategy.on_order(order)

    def _fill_order(self, strategy: StrategyBase, order: LocalOrder) -> None: #模拟交易所的撮合成交
        if self.current_bar is None:
            return
        request = order.request
        # 市价单采用“收盘出信号，次根开盘成交”的回测假设。
        fill_price = request.price or self.current_bar.open #有请求价用请求价，没有就用当前k线的open价
        if request.price is not None:
            if request.side == OrderSide.BUY and request.price < self.current_bar.low: #限价买单判断，当买入请求价格小于当前最低价时不能买入
                return
            if request.side == OrderSide.SELL and request.price > self.current_bar.high: #限价卖单判断，当卖出请求价格高于当前最高价时不能卖出
                return
        slippage = fill_price * self.config.slippage_rate #计算滑点后的价格
        fill_price = fill_price + slippage if request.side == OrderSide.BUY else fill_price - slippage #买入和卖出的实际成交价等于理论成交价加减滑点
        notional = fill_price * request.amount #持仓总价值
        fee = notional * self.config.commission_rate #手续费
        trade = Trade(
            id=str(uuid4()),
            symbol=request.symbol,
            side=request.side,
            amount=request.amount,
            price=fill_price,
            fee=fee,
            traded_at=self.current_bar.datetime, #调用成交k线的时间
        )
        filled = self._apply_trade(strategy, trade, request.position_side, request.reduce_only) #把成交应用到账户和持仓
        if not filled:
            order.status = OrderStatus.REJECTED
            strategy.on_order(order)
            return
        #更新订单状态
        order.filled = request.amount #合约张数
        order.average = fill_price #开仓均价
        order.status = OrderStatus.CLOSED #订单状态枚举，关闭之前的open状态订单
        #保存成交并触发回调
        self.trades.append(trade)
        strategy.trades.append(trade)
        strategy.on_trade(trade)
        strategy.on_order(order)

    def _apply_trade( #更新账户和持仓，这个方法稍微复杂，是当前回测引擎里最需要认真读的地方，细分了合约模式和现货模式
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:  #把一笔成交应用到账户和持仓上。
        if strategy.trading_mode == TradingMode.FUTURE:
            return self._apply_futures_trade(strategy, trade, position_side, reduce_only)
        return self._apply_spot_trade(strategy, trade, position_side, reduce_only)

    def _apply_spot_trade( #现货模式
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        side = position_side or PositionSide.BOTH
        position = strategy.get_position(trade.symbol, side)
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
        previous_amount = position.amount
        new_amount = previous_amount + signed_amount
        if not self.config.allow_short and new_amount < 0:
            return False
        if reduce_only and abs(signed_amount) > abs(previous_amount):
            return False
        notional = trade.price * trade.amount
        cash_change = -(notional + trade.fee) if trade.side == OrderSide.BUY else notional - trade.fee
        if strategy.account.cash + cash_change < 0:
            return False
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
        strategy.account.cash += cash_change
        strategy.account.available = strategy.account.cash
        return True

    def _apply_futures_trade( #合约模式
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        side = position_side or PositionSide.BOTH
        position = strategy.get_position(trade.symbol, side)
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
            if strategy.account.available < required_margin + trade.fee:
                return False
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
            position.margin += required_margin
            strategy.account.margin += required_margin
            strategy.account.cash -= trade.fee
        else:
            close_amount = min(abs(trade.amount), abs(previous_amount))
            close_ratio = close_amount / abs(previous_amount)
            released_margin = position.margin * close_ratio
            realized_pnl = self._realized_pnl(position, trade)
            strategy.account.realized_pnl += realized_pnl
            strategy.account.cash += realized_pnl
            position.margin -= released_margin
            strategy.account.margin -= released_margin
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                opened_amount = abs(signed_amount) - abs(previous_amount)
                opened_notional = trade.price * opened_amount
                required_margin = opened_notional / leverage
                if strategy.account.available < required_margin:
                    return False
                position.entry_price = trade.price
                position.margin += required_margin
                strategy.account.margin += required_margin
            elif new_amount == 0:
                position.entry_price = Decimal("0")
                position.margin = Decimal("0")
        position.amount = new_amount
        position.mark_price = trade.price
        if self.current_bar is not None:
            self._mark_to_market(strategy, self.current_bar)
        return True

    def _realized_pnl(self, position: Position, trade: Trade) -> Decimal: #计算已实现盈亏
        if position.side == PositionSide.SHORT: #空头盈亏
            return (position.entry_price - trade.price) * trade.amount - trade.fee
        return (trade.price - position.entry_price) * trade.amount - trade.fee #多头盈亏

    def _check_liquidation(self, strategy: StrategyBase, bar: BarData) -> bool: #检查强平
        if strategy.trading_mode != TradingMode.FUTURE:
            return False
        if strategy.account.margin <= 0:
            return False
        if strategy.account.equity <= strategy.account.maintenance_margin:
            self._liquidate_all(strategy, bar)
            return True
        return False

    def _liquidate_all(self, strategy: StrategyBase, bar: BarData) -> None: #强平时，引擎会遍历所有持仓，用当前K线close作为强平成交价，生成一笔平仓Trade
        for position in strategy.positions.values():
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
            strategy.account.realized_pnl += realized_pnl
            strategy.account.cash += realized_pnl
            strategy.account.margin -= position.margin
            position.amount = Decimal("0")
            position.entry_price = Decimal("0")
            position.mark_price = bar.close
            position.margin = Decimal("0")
            position.liquidation_price = None
            position.unrealized_pnl = Decimal("0")
            self.trades.append(trade)
            strategy.trades.append(trade)
            strategy.on_trade(trade)
        strategy.account.margin = Decimal("0")
        strategy.account.maintenance_margin = Decimal("0")
        strategy.account.margin_ratio = Decimal("0")
        strategy.account.unrealized_pnl = Decimal("0")
        strategy.account.cash = max(strategy.account.cash, Decimal("0"))
        strategy.account.equity = strategy.account.cash
        strategy.account.available = strategy.account.equity

    def _liquidation_price(self, position: Position) -> Decimal | None:
        if position.amount == 0 or position.entry_price == 0:
            return None
        leverage = self.config.leverage if self.config.leverage > 0 else Decimal("1")
        if position.side == PositionSide.SHORT:
            return position.entry_price * (Decimal("1") + Decimal("1") / leverage - self.config.maintenance_margin_rate)
        return position.entry_price * (Decimal("1") - Decimal("1") / leverage + self.config.maintenance_margin_rate)

    def _mark_to_market(self, strategy: StrategyBase, bar: BarData) -> None: #盯市更新权益，这个方法用于根据当前 K 线价格更新账户权益
        unrealized = Decimal("0") #初始化所有持仓未实现盈亏总和
        position_value = Decimal("0") #初始化现货/多头持仓当前市值
        maintenance_margin = Decimal("0")
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
            if strategy.trading_mode == TradingMode.FUTURE:
                maintenance_margin += bar.close * abs(position.amount) * self.config.maintenance_margin_rate
                position.liquidation_price = self._liquidation_price(position)
            unrealized += position.unrealized_pnl #汇总未实现盈亏
        strategy.account.unrealized_pnl = unrealized #更新账户
        if strategy.trading_mode == TradingMode.FUTURE:
            strategy.account.maintenance_margin = maintenance_margin
            strategy.account.equity = strategy.account.cash + unrealized
            strategy.account.available = strategy.account.equity - strategy.account.margin
            if maintenance_margin == 0:
                strategy.account.margin_ratio = Decimal("0")
            else:
                strategy.account.margin_ratio = maintenance_margin / strategy.account.equity if strategy.account.equity > 0 else Decimal("Infinity")
        else:
            strategy.account.maintenance_margin = Decimal("0")
            strategy.account.margin_ratio = Decimal("0")
            strategy.account.equity = strategy.account.cash + position_value #更新账户
            strategy.account.available = strategy.account.cash
