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
| `leverage` | `Decimal("1")` | 合约杠杆倍数 |
| `margin_mode` | `MarginMode.CROSS` | 保证金模式配置，目前主要作为字段保留 |
| `maintenance_margin_rate` | `Decimal("0.005")` | 维持保证金率 |
| `liquidation_fee_rate` | `Decimal("0.001")` | 强平手续费率 |

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
        if self._check_liquidation(strategy, bar):
            self.equity_curve.append((bar.datetime, strategy.account.equity))
            break
        strategy.on_bar(bar)
        self.equity_curve.append((bar.datetime, strategy.account.equity))
    strategy.on_stop()
    if self.current_bar is not None and self.equity_curve:
        self._mark_to_market(strategy, self.current_bar)
        self.equity_curve[-1] = (self.current_bar.datetime, strategy.account.equity)
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
3. 每根 K 线先按当前价格盯市；
4. 合约模式下检查是否触发强平；
5. 未强平时调用策略逻辑；
6. 记录权益变化；
7. 返回回测结果。
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

### 6.9 强平检查

```python
if self._check_liquidation(strategy, bar):
    self.equity_curve.append((bar.datetime, strategy.account.equity))
    break
```

这一步只对合约模式生效。

回测引擎会检查：

```text
账户权益 equity 是否已经小于等于维持保证金 maintenance_margin
```

如果触发强平，引擎会调用 `_liquidate_all()` 平掉全部仓位，记录当前权益，然后结束回测循环。

这样做的含义是：

```text
强平发生后，策略不会继续执行后面的 on_bar()。
```

---

### 6.10 调用策略逻辑

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

### 6.11 记录权益曲线

```python
self.equity_curve.append((bar.datetime, strategy.account.equity))
```

每根 K 线处理完后记录账户权益。

后续绩效分析会用到。

---

### 6.12 策略结束生命周期

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

### 6.13 返回结果

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
filled = self._apply_trade(strategy, trade, request.position_side, request.reduce_only)
```

`_apply_trade()` 会返回 `True` 或 `False`。

如果返回 `False`，说明这笔订单因为资金不足、保证金不足或不允许的合约反手等原因被拒绝：

```python
if not filled:
    order.status = OrderStatus.REJECTED
    strategy.on_order(order)
    return
```

如果成交成功，这一步会更新：

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

## 10. `_apply_trade`：分发现货和合约成交逻辑

当前版本的 `_apply_trade()` 不再把所有交易都混在一个函数里处理，而是先判断交易模式：

```python
def _apply_trade(
    self,
    strategy: StrategyBase,
    trade: Trade,
    position_side: PositionSide | None,
    reduce_only: bool,
) -> bool:
    if strategy.trading_mode == TradingMode.FUTURE:
        return self._apply_futures_trade(strategy, trade, position_side, reduce_only)
    return self._apply_spot_trade(strategy, trade, position_side, reduce_only)
```

### 10.1 作用

把一笔成交应用到策略的账户和持仓上。

它是当前回测引擎中最核心、也最复杂的方法之一。

现在它会返回布尔值：

| 返回值 | 含义 |
|---|---|
| `True` | 成交可以被账户接受，订单最终关闭 |
| `False` | 成交被拒绝，订单状态变成 `REJECTED` |

这种设计是为了支持：

```text
现货余额不足时拒单；
合约保证金不足时拒单；
不允许的一次性反手合约订单拒单。
```

---

### 10.2 现货和合约为什么要分开？

现货交易和合约交易的账户逻辑完全不同。

现货买入时：

```text
需要支付完整成交额 notional + fee
cash 会直接减少
```

合约开仓时：

```text
不支付完整成交额
只占用 notional / leverage 的保证金
cash 主要扣手续费
```

所以框架拆成：

```python
_apply_spot_trade(...)
_apply_futures_trade(...)
```

这样后续继续扩展合约规则时，不会影响现货逻辑。

---

### 10.3 `_apply_spot_trade`：现货账户逻辑

现货成交仍然使用完整成交额影响现金。

核心规则：

```text
买入：cash -= notional + fee
卖出：cash += notional - fee
```

如果买入后现金会小于 0，就拒绝成交：

```python
if strategy.account.cash + cash_change < 0:
    return False
```

现货持仓仍然会维护：

```text
position.amount
position.entry_price
position.mark_price
account.realized_pnl
account.available
```

这里的 `available` 仍然等于 `cash`，因为现货没有保证金占用。

---

### 10.4 `_apply_futures_trade`：合约账户逻辑

合约成交不会直接扣完整成交额，而是按杠杆占用保证金。

核心变量：

```python
notional = trade.price * trade.amount
leverage = self.config.leverage if self.config.leverage > 0 else Decimal("1")
required_margin = notional / leverage
```

例如：

```text
成交额 notional = 1000
杠杆 leverage = 50
占用保证金 required_margin = 1000 / 50 = 20
```

### 10.5 合约开仓/加仓

当这笔成交属于开仓或加仓时：

```python
if strategy.account.available < required_margin + trade.fee:
    return False
position.margin += required_margin
strategy.account.margin += required_margin
strategy.account.cash -= trade.fee
```

含义：

```text
1. 先检查可用资金是否足够支付保证金和手续费；
2. 仓位保证金增加；
3. 账户总占用保证金增加；
4. cash 只扣手续费，不扣完整成交额。
```

### 10.6 合约平仓/减仓

平仓或减仓时会释放一部分保证金，并计算已实现盈亏：

```python
close_ratio = close_amount / abs(previous_amount)
released_margin = position.margin * close_ratio
realized_pnl = self._realized_pnl(position, trade)
strategy.account.cash += realized_pnl
position.margin -= released_margin
strategy.account.margin -= released_margin
```

含义：

```text
平掉多少比例的仓位，就释放多少比例的保证金；
盈利会增加 cash；
亏损会减少 cash。
```

### 10.7 当前对合约反手的限制

当前版本不允许一笔订单直接从多头反手到空头，或从空头反手到多头：

```python
if previous_amount != 0 and ... and abs(signed_amount) > abs(previous_amount):
    return False
```

更推荐的做法是：

```text
先平掉原仓位；
下一笔订单再开反向仓位。
```

这样逻辑更清楚，也更容易检查保证金和盈亏。

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

当前版本已经按交易模式拆分账户权益计算。

现货模式：

```python
strategy.account.equity = strategy.account.cash + position_value + unrealized
strategy.account.available = strategy.account.cash
```

合约模式：

```python
strategy.account.maintenance_margin = maintenance_margin
strategy.account.equity = strategy.account.cash + unrealized
strategy.account.available = strategy.account.equity - strategy.account.margin
strategy.account.margin_ratio = maintenance_margin / strategy.account.equity
```

也就是：

```text
现货 equity = cash + position_value + unrealized
合约 equity = cash + unrealized_pnl
合约 available = equity - margin
```

合约模式下还会为每个持仓更新预估强平价：

```python
position.liquidation_price = self._liquidation_price(position)
```

---

## 13. 合约强平相关方法

### 13.1 `_check_liquidation`

```python
def _check_liquidation(self, strategy: StrategyBase, bar: BarData) -> bool:
    if strategy.trading_mode != TradingMode.FUTURE:
        return False
    if strategy.account.margin <= 0:
        return False
    if strategy.account.equity <= strategy.account.maintenance_margin:
        self._liquidate_all(strategy, bar)
        return True
    return False
```

含义：

```text
只有合约模式才检查强平；
没有保证金占用就不检查；
当账户权益小于等于维持保证金时，触发强平。
```

### 13.2 `_liquidate_all`

强平时，引擎会遍历所有持仓，用当前 K 线 close 作为强平成交价，生成一笔平仓 `Trade`。

强平后会把仓位重置为：

```text
amount = 0
entry_price = 0
margin = 0
liquidation_price = None
unrealized_pnl = 0
```

账户层面会重置：

```text
margin = 0
maintenance_margin = 0
margin_ratio = 0
unrealized_pnl = 0
equity = cash
available = equity
```

如果强平后 cash 小于 0，当前简化模型会把 cash 截断到 0，避免出现负余额继续参与回测。

### 13.3 `_liquidation_price`

当前强平价是简化估算，不是 Binance 官方完整公式。

多头：

```text
entry_price * (1 - 1 / leverage + maintenance_margin_rate)
```

空头：

```text
entry_price * (1 + 1 / leverage - maintenance_margin_rate)
```

它的作用主要是给策略和回测结果提供一个风险参考。

---

## 14. 一笔买入成交的完整例子

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

## 15. 当前版本的简化假设

当前回测引擎是框架骨架，不是完整生产级回测系统。

读代码时要知道哪些地方是故意简化的。

### 15.1 市价单按 close 成交

当前：

```text
市价单成交价 = 当前 K 线 close
```

现实中市价单成交价取决于盘口深度和实际撮合。

### 15.2 限价单只用 high/low 判断

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

### 15.3 不处理部分成交

当前一旦成交：

```python
order.filled = request.amount
```

表示全部成交。

现实中可能部分成交。

### 15.4 合约模型是简化版

当前已经初步支持：

```text
杠杆
保证金占用和释放
维持保证金
保证金率
预估强平价
强平触发
多头/空头盈亏
```

但还不是交易所级别的完整模型，暂时没有完整支持：

```text
资金费率 funding fee
阶梯维持保证金
逐仓和全仓的完整差异
真实强平撮合过程
保险基金/自动减仓 ADL
多币种保证金
```

---

## 16. 后续可扩展方向

围绕 `backtest.py` 可以继续增强：

### 16.1 撮合引擎增强

支持：

```text
市价单按下一根 open 成交
限价单更精细撮合
部分成交
成交量约束
盘口深度模拟
```

### 16.2 账户模型增强

支持：

```text
现货账户
合约账户
保证金账户
多币种账户
手续费资产
```

### 16.3 合约回测增强

支持：

```text
资金费率 funding fee
阶梯维持保证金
更真实的强平价格
逐仓/全仓完整差异
交易所风险限额
```

### 16.4 风控模块

支持：

```text
最大仓位
最大单笔下单金额
最大亏损
最大回撤
禁止重复下单
```

### 16.5 绩效记录增强

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

## 17. 阅读本文件时的主线

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

## 18. 一句话总结

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
