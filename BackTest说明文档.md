# `crypto_quant/engine/backtest.py` 说明文档

本文档详细解释 `crypto_quant/engine/backtest.py` 文件的设计目的、核心类、方法流程、订单撮合逻辑、账户和持仓更新方式，以及当前版本的简化假设。

`backtest.py` 是当前框架中的回测引擎模块。它负责用历史 K 线驱动策略运行，并模拟订单成交、账户资金变化和持仓变化。

---

## 1. 文件整体定位

文件位置：

```text
crypto_quant/engine/backtest.py
```

它位于引擎层，连接了数据层和策略层。

整体关系：

```text
DataFeed 历史行情数据
        ↓
BacktestEngine 回测引擎
        ↓
StrategyBase.on_bar(bar)
        ↓
策略发出 OrderRequest
        ↓
BacktestEngine 模拟成交
        ↓
更新 LocalOrder / Trade / Position / Account
        ↓
生成 BacktestResult
```

你可以把 `BacktestEngine` 理解为：

```text
历史行情播放器 + 模拟交易所 + 简化账户结算器
```

---

## 2. 文件导入说明

源码：

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from crypto_quant.config import BacktestConfig
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, PositionSide, TradingMode
from crypto_quant.strategy.base import Account, LocalOrder, OrderRequest, Position, StrategyBase, Trade
```

含义：

| 导入项 | 作用 |
|---|---|
| `dataclass` | 定义回测结果数据类 |
| `field` | 给可变字段提供默认工厂，例如 list |
| `datetime` | 记录权益曲线时间 |
| `Decimal` | 高精度资金、价格、数量计算 |
| `uuid4` | 生成本地订单 ID 和成交 ID |
| `BacktestConfig` | 回测配置 |
| `BarData` | 单根 K 线 |
| `DataFeed` | 历史数据源 |
| `OrderSide` | 买卖方向 |
| `OrderStatus` | 订单状态 |
| `PositionSide` | 持仓方向 |
| `TradingMode` | 现货/合约模式 |
| `Account` | 策略账户对象 |
| `LocalOrder` | 本地订单对象 |
| `OrderRequest` | 策略发出的订单请求 |
| `Position` | 持仓对象 |
| `StrategyBase` | 策略基类 |
| `Trade` | 成交记录 |

---

## 3. 回测引擎整体流程

回测引擎的核心方法是：

```python
BacktestEngine.run(strategy, data)
```

整体流程：

```mermaid
flowchart TD
    A[创建 BacktestEngine] --> B[调用 run(strategy, data)]
    B --> C[绑定 engine 到 strategy]
    C --> D[绑定 DataFeed 到 strategy]
    D --> E[设置初始账户资金]
    E --> F[strategy.on_init]
    F --> G[strategy.on_start]
    G --> H[遍历 DataFeed]
    H --> I[设置 current_bar]
    I --> J[按当前 bar 盯市 mark_to_market]
    J --> K[strategy.on_bar bar]
    K --> L{策略是否下单?}
    L -- 否 --> M[记录权益曲线]
    L -- 是 --> N[submit_order]
    N --> O[_fill_order 模拟成交]
    O --> P[_apply_trade 更新账户和持仓]
    P --> M
    M --> H
    H --> Q[strategy.on_stop]
    Q --> R[返回 BacktestResult]
```

---

## 4. `BacktestResult`：回测结果对象

源码：

```python
@dataclass(slots=True)
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[tuple[datetime, Decimal]]
    final_account: Account
    orders: list[LocalOrder] = field(default_factory=list)
```

### 4.1 作用

`BacktestResult` 是回测结束后的结果对象。

它把回测过程中产生的关键结果集中返回给调用者。

例如：

```python
result = engine.run(strategy, data)
```

之后可以访问：

```python
result.trades
result.equity_curve
result.final_account
result.orders
```

### 4.2 字段说明

| 字段 | 类型 | 含义 |
|---|---|---|
| `trades` | `list[Trade]` | 回测中的所有成交记录 |
| `equity_curve` | `list[tuple[datetime, Decimal]]` | 权益曲线，每个元素是 `(时间, 权益)` |
| `final_account` | `Account` | 回测结束后的账户状态 |
| `orders` | `list[LocalOrder]` | 回测中的所有订单 |

### 4.3 `equity_curve` 示例

```python
[
    (datetime(2026, 1, 1, 0, 0), Decimal("10000")),
    (datetime(2026, 1, 1, 0, 1), Decimal("10005")),
    (datetime(2026, 1, 1, 0, 2), Decimal("9998")),
]
```

这表示每根 K 线处理完后的账户总权益。

绩效分析模块会基于它计算：

```text
总收益率
最大回撤
夏普比率
```

### 4.4 为什么 `orders` 使用 `field(default_factory=list)`？

源码：

```python
orders: list[LocalOrder] = field(default_factory=list)
```

不能写成：

```python
orders: list[LocalOrder] = []
```

因为列表是可变对象，多个 `BacktestResult` 可能共享同一个默认列表。

`field(default_factory=list)` 表示每次创建 `BacktestResult` 时，都创建一个新的空列表。

---

## 5. `BacktestEngine.__init__`

源码：

```python
class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.orders: dict[str, LocalOrder] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        self.current_bar: BarData | None = None
```

### 5.1 作用

初始化一个回测引擎对象。

示例：

```python
from decimal import Decimal
from crypto_quant.config import BacktestConfig
from crypto_quant.engine import BacktestEngine

engine = BacktestEngine(
    BacktestConfig(
        initial_cash=Decimal("10000"),
        commission_rate=Decimal("0.0004"),
        slippage_rate=Decimal("0"),
    )
)
```

### 5.2 `config`

```python
self.config = config or BacktestConfig()
```

如果用户传入配置，就使用用户配置。

如果没有传入，就使用默认配置。

`BacktestConfig` 位于：

```text
crypto_quant/config.py
```

当前字段包括：

| 字段 | 默认值 | 含义 |
|---|---|---|
| `initial_cash` | `Decimal("10000")` | 初始资金 |
| `commission_rate` | `Decimal("0.0004")` | 手续费率 |
| `slippage_rate` | `Decimal("0")` | 滑点率 |
| `allow_short` | `True` | 是否允许做空，当前版本预留 |

### 5.3 `orders`

```python
self.orders: dict[str, LocalOrder] = {}
```

保存回测过程中所有订单。

key 是订单 ID，value 是 `LocalOrder`。

### 5.4 `trades`

```python
self.trades: list[Trade] = []
```

保存回测过程中所有成交。

### 5.5 `equity_curve`

```python
self.equity_curve: list[tuple[datetime, Decimal]] = []
```

保存权益曲线。

每根 K 线处理完后追加一条。

### 5.6 `current_bar`

```python
self.current_bar: BarData | None = None
```

保存当前正在处理的 K 线。

为什么需要它？

因为策略下单时只会发出 `OrderRequest`，不会主动传当前 K 线。

回测引擎需要用当前 K 线的：

```text
close
high
low
datetime
```

来模拟成交价格、判断限价单是否成交、生成成交时间。

所以当前 K 线保存在：

```python
self.current_bar
```

---

## 6. `run`：回测主循环

源码：

```python
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
```

### 6.1 作用

`run()` 是整个回测引擎最核心的方法。

它负责：

```text
1. 准备策略运行环境；
2. 遍历历史 K 线；
3. 每根 K 线调用策略逻辑；
4. 记录权益变化；
5. 返回回测结果。
```

---

### 6.2 绑定引擎

```python
strategy.bind_engine(self)
```

把当前 `BacktestEngine` 绑定到策略。

绑定后，策略调用：

```python
self.buy(...)
```

最终会走到：

```python
self.engine.submit_order(self, request)
```

也就是回测引擎的 `submit_order()`。

---

### 6.3 绑定数据

```python
strategy.bind_data(data)
```

把 `DataFeed` 绑定到策略。

绑定后，策略可以使用：

```python
self.data.close[0]
self.data.close[-1]
```

---

### 6.4 设置初始账户

```python
strategy.account = Account(
    cash=self.config.initial_cash,
    equity=self.config.initial_cash,
    available=self.config.initial_cash,
)
```

策略刚创建时账户默认为 0。

回测开始时，回测引擎会用配置里的初始资金重置策略账户。

例如：

```python
initial_cash = Decimal("10000")
```

则账户变为：

```text
cash = 10000
equity = 10000
available = 10000
```

---

### 6.5 策略启动生命周期

```python
strategy.on_init()
strategy.on_start()
```

调用顺序：

```text
on_init → on_start
```

通常：

| 方法 | 适合做什么 |
|---|---|
| `on_init` | 初始化指标缓存、变量、参数 |
| `on_start` | 启动日志、启动前检查 |

---

### 6.6 遍历数据源

```python
for bar in data:
```

这里会触发 `DataFeed.__iter__()`。

每一轮循环，`DataFeed` 会：

```text
1. 推进自己的 _cursor；
2. 推进 open/high/low/close/volume 等 DataLine 的 _cursor；
3. yield 当前 BarData。
```

因此在循环里：

```python
bar
```

就是当前 K 线。

同时策略里的：

```python
self.data.close[0]
```

也已经指向当前 K 线的收盘价。

---

### 6.7 设置当前 K 线

```python
self.current_bar = bar
```

用于后续订单撮合。

如果策略在 `on_bar()` 中下单，`_fill_order()` 会用 `self.current_bar` 来确定成交价和成交时间。

---

### 6.8 盯市更新

```python
self._mark_to_market(strategy, bar)
```

根据当前 K 线的 close 更新：

```text
持仓标记价格
未实现盈亏
账户总权益
```

---

### 6.9 调用策略逻辑

```python
strategy.on_bar(bar)
```

这是策略真正运行的地方。

如果策略满足条件，会调用：

```python
self.buy(...)
self.sell(...)
self.short(...)
self.cover(...)
self.close_position(...)
```

这些方法最终会进入回测引擎的：

```python
submit_order()
```

---

### 6.10 记录权益曲线

```python
self.equity_curve.append((bar.datetime, strategy.account.equity))
```

每根 K 线处理完后记录账户权益。

后续绩效分析会用到。

---

### 6.11 策略结束生命周期

```python
strategy.on_stop()
```

所有 K 线遍历结束后调用。

适合做：

```text
输出总结
保存自定义统计
清理资源
```

---

### 6.12 返回结果

```python
return BacktestResult(
    trades=self.trades,
    equity_curve=self.equity_curve,
    final_account=strategy.account,
    orders=list(self.orders.values()),
)
```

返回完整回测结果。

---

## 7. `submit_order`：接收策略订单

源码：

```python
def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
    order = LocalOrder(id=str(uuid4()), request=request)
    self.orders[order.id] = order
    strategy.orders[order.id] = order
    strategy.on_order(order)
    self._fill_order(strategy, order)
    return order.id
```

### 7.1 作用

当策略调用 `buy()`、`sell()` 等方法时，最终会生成 `OrderRequest`，然后交给回测引擎的 `submit_order()`。

它负责：

```text
1. 创建本地订单 LocalOrder；
2. 保存订单；
3. 触发订单回调；
4. 尝试模拟成交；
5. 返回订单 ID。
```

### 7.2 创建本地订单

```python
order = LocalOrder(id=str(uuid4()), request=request)
```

创建一张本地订单。

订单 ID 使用 `uuid4()` 生成。

默认状态为：

```python
OrderStatus.OPEN
```

### 7.3 保存到引擎订单字典

```python
self.orders[order.id] = order
```

回测引擎保存所有订单。

### 7.4 保存到策略订单字典

```python
strategy.orders[order.id] = order
```

策略也保存订单。

注意：这里保存的是同一个 `LocalOrder` 对象引用。

所以后面引擎更新订单状态，策略里的订单对象也会同步变化。

### 7.5 触发订单回调

```python
strategy.on_order(order)
```

订单刚创建时触发一次。

此时通常状态为：

```python
OrderStatus.OPEN
```

### 7.6 尝试撮合成交

```python
self._fill_order(strategy, order)
```

当前版本创建订单后会立刻尝试成交。

### 7.7 返回订单 ID

```python
return order.id
```

策略调用：

```python
order_id = self.buy("BTC/USDT", Decimal("0.01"))
```

最终拿到的就是这个 ID。

---

## 8. `cancel_order`：撤单

源码：

```python
def cancel_order(self, strategy: StrategyBase, order_id: str) -> None:
    order = self.orders[order_id]
    if order.status == OrderStatus.OPEN:
        order.status = OrderStatus.CANCELED
        strategy.on_order(order)
```

### 8.1 作用

在回测环境中撤销一张订单。

### 8.2 根据订单 ID 找订单

```python
order = self.orders[order_id]
```

从引擎订单字典中取出订单。

### 8.3 只允许撤销 OPEN 订单

```python
if order.status == OrderStatus.OPEN:
```

如果订单还处于打开状态，才允许撤销。

如果订单已经成交、取消、过期，则不处理。

### 8.4 更新状态并回调

```python
order.status = OrderStatus.CANCELED
strategy.on_order(order)
```

订单状态变为取消，并通知策略。

---

## 9. `_fill_order`：模拟订单成交

源码：

```python
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
    trade = Trade(...)
    self._apply_trade(strategy, trade, request.position_side, request.reduce_only)
    order.filled = request.amount
    order.average = fill_price
    order.status = OrderStatus.CLOSED
    self.trades.append(trade)
    strategy.trades.append(trade)
    strategy.on_trade(trade)
    strategy.on_order(order)
```

### 9.1 作用

根据当前 K 线模拟订单成交。

当前版本的撮合逻辑是简化版：

```text
市价单按当前 close 成交；
限价单根据当前 bar 的 high/low 判断是否能成交；
一旦成交就默认全部成交。
```

### 9.2 没有当前 K 线就不处理

```python
if self.current_bar is None:
    return
```

如果当前没有 K 线，就无法判断成交价格。

### 9.3 获取原始订单请求

```python
request = order.request
```

`LocalOrder` 中保存着原始的 `OrderRequest`。

### 9.4 初始成交价

```python
fill_price = request.price or self.current_bar.close
```

含义：

| 订单类型 | 成交价来源 |
|---|---|
| 有 `price` | 使用 `request.price` |
| 没有 `price` | 使用当前 K 线 `close` |

所以：

```text
限价单先以限价作为成交价；
市价单以当前 close 作为成交价。
```

### 9.5 限价买单成交判断

```python
if request.side == OrderSide.BUY and request.price < self.current_bar.low:
    return
```

如果买入限价低于当前 K 线最低价，说明这一根 K 线价格没有跌到你的买价，因此不成交。

例如：

```text
当前 low = 100
买入限价 = 95
```

价格最低只到 100，没有到 95，所以买单不成交。

### 9.6 限价卖单成交判断

```python
if request.side == OrderSide.SELL and request.price > self.current_bar.high:
    return
```

如果卖出限价高于当前 K 线最高价，说明这一根 K 线价格没有涨到你的卖价，因此不成交。

例如：

```text
当前 high = 110
卖出限价 = 120
```

价格最高只到 110，没有到 120，所以卖单不成交。

### 9.7 滑点计算

```python
slippage = fill_price * self.config.slippage_rate
fill_price = fill_price + slippage if request.side == OrderSide.BUY else fill_price - slippage
```

滑点代表实际成交价比理论价格更差。

买入时：

```text
实际成交价 = 理论成交价 + 滑点
```

卖出时：

```text
实际成交价 = 理论成交价 - 滑点
```

例如：

```text
理论价格 = 100000
滑点率 = 0.0001
滑点 = 10
```

买入实际成交价：

```text
100010
```

卖出实际成交价：

```text
99990
```

### 9.8 成交额

```python
notional = fill_price * request.amount
```

成交额：

```text
成交价格 × 成交数量
```

例如：

```text
100000 × 0.01 = 1000
```

### 9.9 手续费

```python
fee = notional * self.config.commission_rate
```

手续费：

```text
成交额 × 手续费率
```

例如：

```text
成交额 = 1000
手续费率 = 0.0004
手续费 = 0.4
```

### 9.10 创建成交记录

```python
trade = Trade(
    id=str(uuid4()),
    symbol=request.symbol,
    side=request.side,
    amount=request.amount,
    price=fill_price,
    fee=fee,
    traded_at=self.current_bar.datetime,
)
```

生成一笔成交记录。

### 9.11 应用成交到账户和持仓

```python
self._apply_trade(strategy, trade, request.position_side, request.reduce_only)
```

这一步会更新：

```text
持仓数量
持仓均价
账户现金
可用资金
已实现盈亏
```

### 9.12 更新订单状态

```python
order.filled = request.amount
order.average = fill_price
order.status = OrderStatus.CLOSED
```

当前版本不处理部分成交。

一旦成交，就认为全部成交。

### 9.13 保存成交并触发回调

```python
self.trades.append(trade)
strategy.trades.append(trade)
strategy.on_trade(trade)
strategy.on_order(order)
```

成交会同时保存在：

```text
引擎 trades
策略 trades
```

然后触发：

```text
on_trade
on_order
```

---

## 10. `_apply_trade`：更新账户和持仓

源码：

```python
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
```

### 10.1 作用

把一笔成交应用到策略的账户和持仓上。

它是当前回测引擎中最核心、也最复杂的方法之一。

---

### 10.2 确定持仓方向

```python
side = position_side or PositionSide.BOTH
```

如果订单请求中指定了 `position_side`，就使用它。

如果没有指定，就默认使用：

```python
PositionSide.BOTH
```

这适用于现货和单向持仓。

---

### 10.3 获取持仓对象

```python
position = strategy.get_position(trade.symbol, side)
```

例如：

```text
BTC/USDT:BOTH
BTC/USDT:SHORT
```

如果持仓不存在，`get_position()` 会自动创建空持仓。

---

### 10.4 计算带方向的成交数量

```python
signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
```

普通逻辑：

| 成交方向 | signed_amount |
|---|---:|
| 买入 | `+amount` |
| 卖出 | `-amount` |

例如：

```text
买入 0.01 → +0.01
卖出 0.01 → -0.01
```

---

### 10.5 合约空头方向修正

```python
if strategy.trading_mode == TradingMode.FUTURE and side == PositionSide.SHORT:
    signed_amount = -signed_amount
```

合约空头中，开空通常是 `SELL`。

普通逻辑下：

```text
SELL 0.01 → -0.01
```

但在 `PositionSide.SHORT` 这条持仓线里，开空应该让空头持仓数量增加。

所以需要反转符号：

```text
-0.01 → +0.01
```

---

### 10.6 计算新旧持仓数量

```python
previous_amount = position.amount
new_amount = previous_amount + signed_amount
```

例如原来空仓：

```text
previous_amount = 0
```

买入 0.01：

```text
new_amount = 0 + 0.01 = 0.01
```

---

### 10.7 成交额

```python
notional = trade.price * trade.amount
```

成交额等于成交价格乘以成交数量。

---

### 10.8 `reduce_only` 分支

```python
if reduce_only:
    strategy.account.realized_pnl += self._realized_pnl(position, trade)
```

如果订单是只减仓，说明这笔成交是平仓性质。

此时计算已实现盈亏。

常见于：

```text
合约平多
合约平空
显式 reduce_only 订单
```

---

### 10.9 开仓或加仓分支

```python
elif previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0):
    total_cost = position.entry_price * abs(previous_amount) + notional
    position.entry_price = total_cost / abs(new_amount)
```

这个条件表示：

```text
原来没仓位；
或者成交方向和原持仓方向一致。
```

这种情况属于：

```text
开仓或加仓。
```

需要更新持仓均价。

#### 示例：从 0 开仓

```text
previous_amount = 0
entry_price = 0
买入数量 = 0.01
买入价格 = 100000
notional = 1000
new_amount = 0.01
entry_price = 1000 / 0.01 = 100000
```

#### 示例：加仓

原持仓：

```text
amount = 0.01
entry_price = 100000
```

再次买入：

```text
amount = 0.01
price = 110000
```

计算：

```text
原成本 = 100000 * 0.01 = 1000
新成本 = 110000 * 0.01 = 1100
总成本 = 2100
新数量 = 0.02
新均价 = 2100 / 0.02 = 105000
```

---

### 10.10 减仓、平仓或反手分支

```python
else:
    strategy.account.realized_pnl += self._realized_pnl(position, trade)
    if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
        position.entry_price = trade.price
```

这个分支表示成交方向和原持仓方向相反。

可能是：

```text
减仓
完全平仓
反手开仓
```

例如：

| 原持仓 | 新成交 | 含义 |
|---|---|---|
| 多 0.02 | 卖 0.01 | 减仓 |
| 多 0.02 | 卖 0.02 | 平仓 |
| 多 0.02 | 卖 0.03 | 反手为空 0.01 |

当前版本对这些情况做了简化处理。

---

### 10.11 更新持仓数量和标记价

```python
position.amount = new_amount
position.mark_price = trade.price
```

更新持仓数量和最新价格。

---

### 10.12 更新账户现金

源码：

```python
strategy.account.cash -= notional + trade.fee if trade.side == OrderSide.BUY else -notional + trade.fee
```

这行等价于：

```python
if trade.side == OrderSide.BUY:
    strategy.account.cash -= notional + trade.fee
else:
    strategy.account.cash -= -notional + trade.fee
```

卖出分支也可以理解为：

```python
strategy.account.cash += notional - trade.fee
```

所以：

| 成交方向 | 现金变化 |
|---|---|
| 买入 | 减少成交额和手续费 |
| 卖出 | 增加成交额，扣除手续费 |

---

### 10.13 更新可用资金

```python
strategy.account.available = strategy.account.cash
```

当前版本简化处理：

```text
可用资金 = 现金
```

后续如果完善合约保证金，需要区分：

```text
cash
available
margin
```

---

## 11. `_realized_pnl`：计算已实现盈亏

源码：

```python
def _realized_pnl(self, position: Position, trade: Trade) -> Decimal:
    if position.side == PositionSide.SHORT:
        return (position.entry_price - trade.price) * trade.amount - trade.fee
    return (trade.price - position.entry_price) * trade.amount - trade.fee
```

### 11.1 作用

计算平仓时产生的已实现盈亏。

### 11.2 多头盈亏

如果不是空头，使用：

```text
卖出价 - 买入均价
```

公式：

```python
(trade.price - position.entry_price) * trade.amount - trade.fee
```

例子：

```text
entry_price = 100000
trade.price = 110000
amount = 0.01
fee = 0.44
```

盈亏：

```text
(110000 - 100000) * 0.01 - 0.44 = 99.56
```

### 11.3 空头盈亏

空头是价格下跌赚钱。

公式：

```python
(position.entry_price - trade.price) * trade.amount - trade.fee
```

例子：

```text
entry_price = 100000
trade.price = 90000
amount = 0.01
fee = 0.36
```

盈亏：

```text
(100000 - 90000) * 0.01 - 0.36 = 99.64
```

---

## 12. `_mark_to_market`：盯市更新权益

源码：

```python
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
```

### 12.1 作用

每根 K 线开始处理时，根据当前 K 线收盘价更新账户浮动盈亏和总权益。

盯市可以理解为：

```text
用当前市场价格重新估算账户当前价值。
```

### 12.2 初始化变量

```python
unrealized = Decimal("0")
position_value = Decimal("0")
```

| 变量 | 含义 |
|---|---|
| `unrealized` | 所有持仓未实现盈亏总和 |
| `position_value` | 非空头持仓当前市值 |

### 12.3 遍历所有持仓

```python
for position in strategy.positions.values():
```

一个策略可能同时有多个交易对或多个方向的持仓。

### 12.4 更新标记价格

```python
position.mark_price = bar.close
```

当前版本用 K 线 close 作为标记价格。

### 12.5 空仓处理

```python
if position.amount == 0:
    position.unrealized_pnl = Decimal("0")
    continue
```

如果没有持仓，浮动盈亏为 0。

### 12.6 空头未实现盈亏

```python
position.unrealized_pnl = (position.entry_price - bar.close) * abs(position.amount)
```

空头价格下跌赚钱。

例如：

```text
entry_price = 100000
bar.close = 90000
amount = 0.01
```

浮盈：

```text
(100000 - 90000) * 0.01 = 100
```

### 12.7 多头/现货未实现盈亏

```python
position.unrealized_pnl = (bar.close - position.entry_price) * position.amount
position_value += bar.close * position.amount
```

多头价格上涨赚钱。

同时计算当前持仓市值。

例如：

```text
entry_price = 100000
bar.close = 101000
amount = 0.01
```

浮盈：

```text
(101000 - 100000) * 0.01 = 10
```

持仓市值：

```text
101000 * 0.01 = 1010
```

### 12.8 汇总未实现盈亏

```python
unrealized += position.unrealized_pnl
```

### 12.9 更新账户

```python
strategy.account.unrealized_pnl = unrealized
strategy.account.equity = strategy.account.cash + position_value + unrealized
```

当前版本的权益公式是：

```text
equity = cash + position_value + unrealized
```

需要注意：这是初始简化写法。对于现货来说，严格情况下更常见的是：

```text
equity = cash + position_value
```

对于合约来说，更常见的是：

```text
equity = cash + unrealized_pnl
```

所以后续可以根据 `TradingMode` 拆分权益计算逻辑。

---

## 13. 一笔买入成交的完整例子

假设：

```text
初始资金 = 10000 USDT
BTC 当前 close = 100000
买入数量 = 0.01
手续费率 = 0.0004
滑点率 = 0
```

策略执行：

```python
self.buy("BTC/USDT", Decimal("0.01"))
```

流程：

```text
1. StrategyBase.buy()
2. StrategyBase.submit_order()
3. 创建 OrderRequest
4. BacktestEngine.submit_order()
5. 创建 LocalOrder，状态 OPEN
6. _fill_order() 按当前 close 成交
7. notional = 100000 * 0.01 = 1000
8. fee = 1000 * 0.0004 = 0.4
9. 创建 Trade
10. _apply_trade() 更新账户和持仓
11. position.amount = 0.01
12. position.entry_price = 100000
13. cash = 10000 - 1000 - 0.4 = 8999.6
14. order.status = CLOSED
15. strategy.on_trade(trade)
16. strategy.on_order(order)
```

---

## 14. 当���版本的简化假设

当前回测引擎是框架骨架，不是完整生产级回测系统。

读代码时要知道哪些地方是故意简化的。

### 14.1 市价单按 close 成交

当前：

```text
市价单成交价 = 当前 K 线 close
```

现实中市价单成交价取决于盘口深度和实际撮合。

### 14.2 限价单只用 high/low 判断

买单：

```text
如果 limit price >= low，则认为可能成交
```

卖单：

```text
如果 limit price <= high，则认为可能成交
```

现实中还要考虑：

```text
价格路径
成交量
盘口深度
排队位置
```

### 14.3 不处理部分成交

当前一旦成交：

```python
order.filled = request.amount
```

表示全部成交。

现实中可能部分成交。

### 14.4 合约模型还不完整

当前只初步支持：

```text
PositionSide.SHORT
reduce_only
```

还没有完整支持：

```text
杠杆
保证金
资金费率
强平价
逐仓/全仓
```

### 14.5 账户权益公式需要后续细化

当前：

```text
equity = cash + position_value + unrealized
```

后续建议按模式拆分：

```text
现货：equity = cash + position_value
合约：equity = cash + unrealized_pnl
```

---

## 15. 后续可扩展方向

围绕 `backtest.py` 可以继续增强：

### 15.1 撮合引擎增强

支持：

```text
市价单按下一根 open 成交
限价单更精细撮合
部分成交
成交量约束
盘口深度模拟
```

### 15.2 账户模型增强

支持：

```text
现货账户
合约账户
保证金账户
多币种账户
手续费资产
```

### 15.3 合约回测增强

支持：

```text
杠杆
逐仓/全仓
资金费率
强平价格
保证金占用
```

### 15.4 风控模块

支持：

```text
最大仓位
最大单笔下单金额
最大亏损
最大回撤
禁止重复下单
```

### 15.5 绩效记录增强

支持：

```text
逐笔订单明细
逐笔成交明细
每日权益
每日收益
手续费统计
滑点统计
```

---

## 16. 阅读本文件时的主线

建议记住这条主线：

```text
run()
  ↓
for bar in data
  ↓
strategy.on_bar(bar)
  ↓
strategy 下单
  ↓
submit_order()
  ↓
_fill_order()
  ↓
_apply_trade()
  ↓
_mark_to_market()
  ↓
BacktestResult
```

更简单地说：

```text
run 负责驱动策略；
submit_order 负责接收订单；
_fill_order 负责模拟成交；
_apply_trade 负责更新账户和持仓；
_mark_to_market 负责更新权益；
BacktestResult 负责返回结果。
```

---

## 17. 一句话总结

`backtest.py` 是当前框架的回测引擎。

它负责：

```text
遍历历史 K 线；
调用策略生命周期方法；
接收策略订单；
模拟成交；
生成成交记录；
更新账户和持仓；
记录权益曲线；
返回回测结果。
```

当前实现保持简洁，适合学习框架主线；后续可以继续增强撮合精度、账户模型、合约保证金、资金费率和风控能力。
