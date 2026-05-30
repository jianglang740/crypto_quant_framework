# `run_testnet_recursive_cusum_reversion_strategy.py` 说明文档

本文档对应脚本：

```text
crypto_quant_framework-main/real/run_testnet_recursive_cusum_reversion_strategy.py
```

它是从回测脚本迁移出来的测试网脚本，源脚本是：

```text
crypto_quant_framework-main/my_strategys/run_recursive_cusum_reversion_strategy.py
```

这个脚本的目标不是寻找新策略，也不是直接准备主网实盘，而是演示一件非常重要的事情：

> 当一个逻辑性比较强的回测策略迁移到测试网/实盘时，策略信号逻辑要尽量保持一致，但数据来源、订单执行、账户持仓同步、数据库记录方式都会发生明显变化。

---

## 1. 脚本定位

这个脚本是一个 **Binance 合约测试网递归 CUSUM 反转策略测试脚本**。

它做的事情包括：

```text
读取 Binance 测试网 5m K 线
→ 按回测脚本同样的递归 CUSUM 方法生成信号
→ 在每根新收盘 K 线上执行 on_bar()
→ 根据信号做多空反转
→ 根据止盈/止损平仓
→ 调用 Binance 测试网真实下单接口
→ 查询订单状态和成交记录
→ 同步测试网账户和合约持仓
→ 写入 MySQL 的 run/order/trade/snapshot/equity 数据
→ dashboard 可通过数据库观察运行结果
```

它和 `run_testnet_smoke_strategy.py` 的区别是：

| 脚本 | 主要目的 | 数据来源 | 策略逻辑位置 |
|---|---|---|---|
| `run_testnet_smoke_strategy.py` | 验证交易链路和数据库链路 | ticker 当前行情快照 | `main()` 的 while 循环 |
| `run_testnet_recursive_cusum_reversion_strategy.py` | 演示回测策略如何迁移到测试网 | 5m K 线 | `StrategyBase.on_bar()` |

因此，这个脚本更接近“真实策略迁移”的结构。

---

## 2. 重要安全边界

这个脚本连接的是 Binance 测试网，并且使用 `sandbox=True`。

但是仍然要注意：

1. 它会真实调用测试网下单接口。
2. 它会真实写入 MySQL。
3. 它是合约策略，不是现货策略。
4. 它包含做多、做空、平多、平空逻辑。
5. 它不应该直接复制到主网运行。
6. 主网运行前必须重新审查交易数量、杠杆、保证金模式、止损、异常处理和风控。

脚本中没有硬编码 API key、secret、数据库密码。

敏感信息仍然从环境变量或 `.env` 读取。

---

## 3. 参数为什么写在脚本里

用户要求：

> 参数、交易对等环境变量放到脚本里，只有数据库和 API 等敏感信息才从 `.env` 读取。

所以这个脚本把策略和交易参数写成了顶部常量：

```python
SYMBOL = "ETH/USDT"
TIMEFRAME = "5m"

THRESHOLD = Decimal("0.07")
TAKE_PROFIT_RATE = Decimal("0.018")
STOP_LOSS_RATE = Decimal("0.033")
POSITION_RATIO = Decimal("0.30")
LEVERAGE = Decimal("10")
MARGIN_MODE = MarginMode.CROSS

KLINE_LIMIT = 500
SNAPSHOT_INTERVAL_SECONDS = 30
MAX_CYCLES = 0
```

这和原回测脚本保持对应：

```python
SYMBOL = "ETH/USDT"
TIMEFRAME = "5m"
threshold=Decimal("0.07")
take_profit_rate=Decimal("0.018")
stop_loss_rate=Decimal("0.033")
position_ratio=Decimal("0.30")
leverage=Decimal("10")
```

也就是说，策略层面的核心参数没有放到 `.env` 里。

`.env` 只负责敏感信息，例如：

```text
CRYPTO_QUANT_BINANCE_FUTURES_TESTNET_API_KEY
CRYPTO_QUANT_BINANCE_FUTURES_TESTNET_SECRET_KEY
CRYPTO_QUANT_MYSQL_PASSWORD
```

---

## 4. 为什么必须用合约测试网

原回测策略是：

```python
super().__init__(trading_mode=TradingMode.FUTURE)
```

并且包含：

```python
self.buy(...)
self.short(...)
self.cover(...)
self.close_position(...)
```

这说明它不是一个普通现货策略。

它的核心行为是：

```text
信号 = 1  → 反转到多头
信号 = -1 → 反转到空头
```

如果强行迁移成现货测试网，就会出现问题：

- 现货可以买入和卖出；
- 但现货没有真正的开空；
- `short()` 和 `cover()` 的语义无法完整保留；
- 多空反转策略会被改坏。

所以这个测试脚本使用：

```python
trading_mode=TradingMode.FUTURE
```

并且 Binance 配置里使用：

```python
BinanceConfig(
    trading_mode=TradingMode.FUTURE,
    sandbox=True,
)
```

这样才能尽量保留回测策略里的合约多空语义。

---

## 5. 顶部路径处理

脚本顶部有：

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
```

这段代码的作用是让脚本无论从哪里启动，都能导入项目里的 `crypto_quant` 包。

假设脚本路径是：

```text
crypto_quant_framework-main/real/run_testnet_recursive_cusum_reversion_strategy.py
```

那么：

```python
Path(__file__).resolve()
```

得到当前脚本的绝对路径。

```python
.parents[0]
```

是：

```text
crypto_quant_framework-main/real
```

```python
.parents[1]
```

是：

```text
crypto_quant_framework-main
```

也就是项目根目录。

然后：

```python
sys.path.insert(0, str(PROJECT_ROOT))
```

把项目根目录放到 Python 模块搜索路径最前面。

这样下面这些导入才能稳定工作：

```python
from crypto_quant.config import BinanceConfig, MySQLConfig
from crypto_quant.data import BarData, DataFeed, MarketDataFetcher
from crypto_quant.database import TradingRepository
from crypto_quant.exchange import BinanceClient
from crypto_quant.strategy.base import StrategyBase
```

---

## 6. 从回测脚本迁移过来的主逻辑

### 6.1 策略类名称

测试网脚本里保留了同一类策略结构：

```python
class RecursiveCusumReversionFuturesStrategy(StrategyBase):
```

它仍然继承：

```python
StrategyBase
```

并且仍然是合约模式：

```python
super().__init__(trading_mode=TradingMode.FUTURE)
```

测试网版本的 `name` 改成了：

```python
name = "testnet_recursive_cusum_reversion_futures"
```

这样数据库中可以看出这是测试网版本，而不是普通回测版本。

---

### 6.2 CUSUM 信号生成逻辑

回测脚本中的核心信号逻辑是：

```python
df = self.data.to_dataframe()
close = df["close"].astype(float)
log_return = np.log(close / close.shift(1)).fillna(0)
threshold = float(self.threshold)
signals = [0] * len(df)
pos_sum = 0.0
neg_sum = 0.0
for i in range(1, len(df)):
    value = float(log_return.iloc[i])
    pos_sum = max(0.0, pos_sum + value)
    neg_sum = min(0.0, neg_sum + value)
    if pos_sum >= threshold:
        signals[i] = 1
        pos_sum = 0.0
        neg_sum = 0.0
    elif neg_sum <= -threshold:
        signals[i] = -1
        pos_sum = 0.0
        neg_sum = 0.0
```

测试网脚本中仍然保留这套逻辑。

含义是：

```text
用 `numpy` 计算 close 的对数收益率
→ 递归累加正向收益 pos_sum
→ 递归累加负向收益 neg_sum
→ 正向累积超过 threshold，生成信号 1
→ 负向累积跌破 -threshold，生成信号 -1
→ 出信号后清空正负累积值
```

这就是“递归 CUSUM”的核心。

---

### 6.3 on_bar 主逻辑

回测脚本的 `on_bar()` 是：

```python
if self._check_take_profit_stop_loss(bar):
    return

if signal == 1:
    self._reverse_to_long(bar)
elif signal == -1:
    self._reverse_to_short(bar)
```

测试网脚本保留了同样顺序。

这点很关键。

它表示每根 K 线到来时，先检查已有仓位是否触发止盈或止损。

如果触发了，就先平仓，然后本轮不再继续反转。

如果没有触发止盈止损，才根据信号做多空反转。

执行顺序是：

```text
新 K 线
→ 找当前信号
→ 先检查止盈止损
→ 如果止盈/止损触发，平仓并结束本轮
→ 如果没有触发，再看 CUSUM 信号
→ signal = 1，反转到多
→ signal = -1，反转到空
```

---

### 6.4 止盈止损逻辑

多头止盈止损：

```python
pnl_rate = bar.close / long_position.entry_price - Decimal("1")
```

含义是：

```text
当前收盘价 / 多头开仓价 - 1
```

如果：

```python
pnl_rate >= take_profit_rate
```

说明多头盈利达到止盈比例。

如果：

```python
pnl_rate <= -stop_loss_rate
```

说明多头亏损达到止损比例。

空头止盈止损：

```python
pnl_rate = short_position.entry_price / bar.close - Decimal("1")
```

空头的盈利方向和多头相反。

如果价格下跌，`entry_price / close - 1` 会变大，表示空头盈利。

---

### 6.5 反转到多头

```python
def _reverse_to_long(self, bar: BarData) -> None:
    long_position = self.get_position(bar.symbol, PositionSide.BOTH)
    short_position = self.get_position(bar.symbol, PositionSide.SHORT)
    if not short_position.is_flat:
        self.cover(bar.symbol, abs(short_position.amount))
    if long_position.is_flat:
        self.buy(bar.symbol, self._order_amount(bar.close))
```

含义是：

```text
如果当前有空头 → 先平空
如果当前没有多头 → 再开多
```

在测试网执行时：

```python
self.cover(...)
```

会变成 Binance 合约测试网的买入平空单。

```python
self.buy(...)
```

会变成 Binance 合约测试网的买入开多单。

---

### 6.6 反转到空头

```python
def _reverse_to_short(self, bar: BarData) -> None:
    long_position = self.get_position(bar.symbol, PositionSide.BOTH)
    short_position = self.get_position(bar.symbol, PositionSide.SHORT)
    if not long_position.is_flat:
        self.close_position(bar.symbol, PositionSide.BOTH)
    if short_position.is_flat:
        self.short(bar.symbol, self._order_amount(bar.close))
```

含义是：

```text
如果当前有多头 → 先平多
如果当前没有空头 → 再开空
```

在测试网执行时：

```python
self.close_position(...)
```

会变成 Binance 合约测试网的卖出平多单。

```python
self.short(...)
```

会变成 Binance 合约测试网的卖出开空单。

---

### 6.7 仓位大小计算

原回测脚本是：

```python
def _order_amount(self, price: Decimal) -> Decimal:
    leverage = self.engine.config.leverage if self.engine is not None else Decimal("1")
    amount = self.account.available * leverage * self.position_ratio / price
    return max(amount, Decimal("0"))
```

测试网脚本保持一致。

含义是：

```text
下单数量 = 可用资金 × 杠杆 × 仓位比例 / 当前价格
```

例如：

```text
available = 1000 USDT
leverage = 10
position_ratio = 0.30
price = 3000 USDT
```

则：

```text
amount = 1000 × 10 × 0.30 / 3000 = 1 ETH
```

注意：

这里使用的是测试网账户同步后的 `strategy.account.available`。

所以测试网里能下多少单，不再由回测初始资金决定，而是由测试网账户真实可用保证金决定。

---

## 7. 和回测脚本最大的结构差异

回测脚本的主流程是：

```python
data = load_bars_from_csv(...)
strategy = RecursiveCusumReversionFuturesStrategy(...)
engine = BacktestEngine(...)
result = engine.run(strategy, data)
```

回测时：

```text
CSV 历史 K 线
→ BacktestEngine 一根一根喂给 strategy.on_bar()
→ engine 模拟成交
→ engine 更新账户和持仓
→ 最后生成 result
```

测试网脚本没有用 `BacktestEngine`。

测试网脚本的主流程是：

```text
Binance 测试网抓取最近 5m K 线
→ 找到新收盘 K 线
→ 手动绑定 DataFeed
→ 调用 strategy.on_init() 重新计算信号
→ 对新 K 线调用 strategy.on_bar()
→ 策略发出订单请求
→ TestnetOrderExecutionEngine.submit_order() 接住订单请求
→ Binance 测试网真实下单
→ 保存订单和成交
→ 同步账户和持仓
→ 保存数据库快照
```

也就是说：

```text
回测：BacktestEngine 负责撮合和账户变化
测试网：交易所负责成交，脚本负责查询、同步和入库
```

---

## 8. 为什么仍然使用 DataFeed

虽然这是测试网脚本，但它仍然使用：

```python
DataFeed
BarData
```

原因是原策略逻辑依赖：

```python
self.data.to_dataframe()
self.data.cursor
```

如果不用 `DataFeed`，就必须重写策略逻辑。

为了最大限度保持回测逻辑一致，测试网脚本仍然把 Binance 返回的 K 线包装成框架里的 `DataFeed`。

相关函数是：

```python
def latest_closed_bars(fetcher: MarketDataFetcher) -> list[BarData]:
    bars = fetcher.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=KLINE_LIMIT)
    if len(bars) < 2:
        return []
    return bars[:-1]
```

这里刻意使用：

```python
bars[:-1]
```

因为 Binance 返回的最后一根 K 线通常可能还没完全收盘。

策略只处理已经收盘的 K 线，避免用未完成 K 线产生信号。

---

## 9. 如何避免重复处理同一根 K 线

测试网脚本维护了：

```python
last_processed_at
```

它记录上一根已经处理过的 K 线时间。

处理新 K 线时：

```python
if last_processed_at is not None and bar.datetime <= last_processed_at:
    continue
```

含义是：

```text
如果这根 K 线时间不晚于上次处理时间，就跳过
```

这样脚本每隔 30 秒轮询一次，但不会每 30 秒都重复对同一根 5m K 线下单。

这点和 smoke 脚本很不一样。

smoke 脚本用 ticker，所以每个循环都可以按当前价判断。

这个脚本用 5m K 线，所以只应该在新收盘 K 线出现时运行策略逻辑。

---

## 10. 为什么 `SNAPSHOT_INTERVAL_SECONDS = 30` 不等于 K 线周期

脚本里有两个时间概念：

```python
TIMEFRAME = "5m"
SNAPSHOT_INTERVAL_SECONDS = 30
```

它们不是同一件事。

| 参数 | 含义 |
|---|---|
| `TIMEFRAME = "5m"` | 策略使用 5 分钟 K 线计算信号 |
| `SNAPSHOT_INTERVAL_SECONDS = 30` | 脚本每 30 秒轮询一次行情、账户和数据库快照 |

所以：

```text
5m 是策略数据周期
30s 是脚本运行检查周期
```

脚本每 30 秒检查一次有没有新的 5m 收盘 K 线。

如果没有新 K 线，就不会重复执行 `on_bar()`。

---

## 11. 测试网执行引擎

为了让策略仍然可以调用：

```python
self.buy()
self.short()
self.cover()
self.close_position()
```

脚本定义了一个轻量级执行引擎：

```python
class TestnetOrderExecutionEngine:
```

它不是回测引擎。

它的作用是接住 `StrategyBase.submit_order()` 产生的 `OrderRequest`，然后转换成 Binance 测试网订单。

核心入口是：

```python
def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
```

执行流程是：

```text
策略发出 OrderRequest
→ 检查下单数量是否大于 0
→ 调用 client.create_order()
→ 保存订单到 orders 表
→ 查询交易所订单状态
→ 更新订单状态
→ 查询订单成交记录
→ 保存成交到 trades 表
→ 更新本地 LocalOrder
→ 同步账户和持仓
```

---

## 12. positionSide 的转换

回测脚本中，多头普通仓位使用：

```python
PositionSide.BOTH
```

空头使用：

```python
PositionSide.SHORT
```

但 Binance 合约测试网在双向持仓语义下通常需要：

```text
LONG
SHORT
```

所以测试网脚本里有一个转换：

```python
def _exchange_position_side(self, request: OrderRequest) -> PositionSide | None:
    if request.position_side == PositionSide.SHORT:
        return PositionSide.SHORT
    if request.position_side == PositionSide.BOTH or request.position_side is None:
        return PositionSide.LONG
    return request.position_side
```

含义是：

```text
框架里的 BOTH 多头槽位 → 交易所下单时转成 LONG
框架里的 SHORT 空头槽位 → 交易所下单时保持 SHORT
```

这样能尽量保持回测策略写法不变，同时适配 Binance 合约接口。

---

## 13. 账户和持仓同步

回测时，账户和持仓由 `BacktestEngine` 直接计算。

测试网时，账户和持仓必须从交易所同步。

脚本中对应函数是：

```python
def sync_account_and_positions(strategy: StrategyBase, client: BinanceClient) -> None:
```

它读取：

```python
client.fetch_balance()
client.fetch_positions([SYMBOL])
```

然后更新：

```python
strategy.account
strategy.positions
```

这一步非常重要。

因为策略里的止盈止损依赖：

```python
long_position.entry_price
short_position.entry_price
position.amount
strategy.account.available
```

如果不从交易所同步账户和持仓，测试网脚本就不知道真实仓位是多少，也无法正确判断止盈止损和下单数量。

---

## 14. 数据库写入内容

脚本会创建一条运行记录：

```python
repository.create_run(...)
```

写入：

```text
strategy_runs
```

每次下单后写入或更新：

```text
orders
trades
```

每轮循环写入：

```text
account_snapshots
position_snapshots
equity_curve
```

因此 dashboard 可以看到：

- 当前运行；
- 账户权益；
- 持仓快照；
- 订单记录；
- 成交记录；
- 权益曲线。

---

## 15. 主流程详解

主函数结构是：

```python
def main() -> None:
    client = BinanceClient(binance_config_from_env())
    client.load_markets()
    configure_futures_account(client)
    fetcher = MarketDataFetcher(client)

    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)

    strategy = RecursiveCusumReversionFuturesStrategy()
```

第一段做三件事：

```text
创建 Binance 测试网客户端
→ 加载市场信息
→ 设置合约保证金模式和杠杆
→ 创建行情抓取器
→ 创建 MySQL 连接
→ 创建策略实例
```

然后：

```python
execution_engine = TestnetOrderExecutionEngine(client, repository, RUN_ID)
strategy.bind_engine(execution_engine)
```

这一步很关键。

回测时绑定的是：

```python
BacktestEngine
```

测试网时绑定的是：

```python
TestnetOrderExecutionEngine
```

策略本身仍然调用：

```python
self.buy()
self.short()
self.cover()
self.close_position()
```

但订单最终不是被模拟成交，而是被测试网执行引擎发送到 Binance 测试网。

---

## 16. 循环逻辑

主循环是：

```python
while MAX_CYCLES <= 0 or cycle < MAX_CYCLES:
```

如果：

```python
MAX_CYCLES = 0
```

表示无限运行，直到手动停止。

每轮循环：

```text
同步账户和持仓
→ 抓取最近 K 线
→ 过滤未收盘 K 线
→ 处理新收盘 K 线
→ 同步账户和持仓
→ 保存账户/持仓/权益快照
→ sleep 30 秒
```

对应代码：

```python
sync_account_and_positions(strategy, client)
bars = latest_closed_bars(fetcher)
last_processed_at = process_new_closed_bars(strategy, bars, last_processed_at)
sync_account_and_positions(strategy, client)
record_snapshot(repository, strategy, run.run_id)
time.sleep(SNAPSHOT_INTERVAL_SECONDS)
```

---

## 17. 停止和异常处理

如果手动按 `Ctrl+C`：

```python
except KeyboardInterrupt:
    repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="stopped")
```

数据库中的运行状态会变成：

```text
stopped
```

如果运行中报错：

```python
except Exception:
    session.rollback()
    repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="failed")
    raise
```

数据库中的运行状态会变成：

```text
failed
```

如果 `MAX_CYCLES` 设置成正数，并且正常跑完：

```python
strategy.on_stop()
repository.finish_run(..., status="finished")
```

数据库中的运行状态会变成：

```text
finished
```

注意：

`on_stop()` 会尝试平掉多头和空头。

如果是无限运行并用 `Ctrl+C` 停止，脚本当前为了安全没有在 `KeyboardInterrupt` 分支自动平仓，只是把运行标记为 stopped。

这是为了避免用户只是想停止脚本观察，却被脚本自动发出平仓单。

---

## 18. 环境变量

脚本内固定了策略参数和交易对。

但以下敏感信息仍然需要来自环境变量或 `.env`。

### Binance 测试网 API

优先读取：

```text
CRYPTO_QUANT_BINANCE_FUTURES_TESTNET_API_KEY
CRYPTO_QUANT_BINANCE_FUTURES_TESTNET_SECRET_KEY
```

脚本不再回退读取 `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_SECRET_KEY`，避免误用之前申请的现货测试网 API。

### MySQL

支持：

```text
CRYPTO_QUANT_MYSQL_HOST
CRYPTO_QUANT_MYSQL_PORT
CRYPTO_QUANT_MYSQL_USERNAME
CRYPTO_QUANT_MYSQL_PASSWORD
CRYPTO_QUANT_MYSQL_DATABASE
```

也兼容：

```text
MYSQL_HOST
MYSQL_PORT
MYSQL_USER
MYSQL_PASSWORD
MYSQL_DATABASE
```

### 代理

如果需要代理：

```text
CRYPTO_QUANT_BINANCE_PROXY_URL
```

或：

```text
BINANCE_PROXY_URL
```

---

## 19. 运行方式

在项目根目录运行：

```bash
python3 real/run_testnet_recursive_cusum_reversion_strategy.py
```

建议先把：

```python
MAX_CYCLES = 0
```

临时改成较小数字，例如：

```python
MAX_CYCLES = 3
```

这样脚本只跑几轮，方便观察数据库写入和控制风险。

---

## 20. 和原回测脚本逐项对照

| 回测脚本 | 测试网脚本 | 是否保持 |
|---|---|---|
| `SYMBOL = "ETH/USDT"` | `SYMBOL = "ETH/USDT"` | 保持 |
| `TIMEFRAME = "5m"` | `TIMEFRAME = "5m"` | 保持 |
| `TradingMode.FUTURE` | `TradingMode.FUTURE` | 保持 |
| `threshold=0.07` | `THRESHOLD = 0.07` | 保持 |
| `take_profit_rate=0.018` | `TAKE_PROFIT_RATE = 0.018` | 保持 |
| `stop_loss_rate=0.033` | `STOP_LOSS_RATE = 0.033` | 保持 |
| `position_ratio=0.30` | `POSITION_RATIO = 0.30` | 保持 |
| `leverage=10` | `LEVERAGE = 10` | 保持 |
| CSV K 线 | Binance 测试网 K 线 | 数据来源改变 |
| `BacktestEngine` 模拟成交 | Binance 测试网真实撮合 | 执行方式改变 |
| 回测账户 | 测试网账户 | 账户来源改变 |
| `PerformanceAnalyzer` | MySQL + dashboard 观察 | 结果观察方式改变 |

---

## 21. 迁移回测策略到测试网时真正要注意什么

通过这个脚本可以看到，迁移不是简单复制 `on_bar()`。

真正要重点处理的是：

1. **数据周期是否一致**
   - 回测用 5m，测试网也应该用 5m。
   - 不要把 5m 策略随便改成 ticker 策略。

2. **是否只使用收盘 K 线**
   - 回测天然使用已完成历史 K 线。
   - 测试网实时抓 K 线时，最后一根可能还没收盘。
   - 所以脚本用了 `bars[:-1]`。

3. **策略状态是否一致**
   - 回测中 `self.data.cursor` 由回测引擎推进。
   - 测试网中需要自己用 `DataFeed` 包装 K 线并推进。

4. **订单语义是否一致**
   - 回测里的 `short()` 必须对应合约开空。
   - 不能悄悄改成现货卖出。

5. **持仓同步是否准确**
   - 止盈止损依赖 entry price。
   - 仓位大小依赖 available。
   - 所以必须从交易所同步账户和持仓。

6. **数据库链路是否完整**
   - run、order、trade、snapshot、equity 都要写入。
   - 否则 dashboard 无法观察测试网运行。

7. **异常处理是否保守**
   - 网络错误、订单查询延迟、交易所返回异常都可能发生。
   - 测试网脚本需要比回测脚本更关注这些问题。

---

## 22. 一个重要差异：回测是一口气跑完，测试网是不断等待

回测脚本：

```text
读取一年历史数据
→ 几秒内跑完整个历史区间
→ 输出最终绩效
```

测试网脚本：

```text
每 30 秒检查一次
→ 等待新的 5m K 线收盘
→ 只处理新出现的 K 线
→ 持续写入数据库
```

所以测试网脚本看起来会更“啰嗦”。

这不是策略逻辑变复杂了，而是实盘环境需要处理：

```text
等待
同步
下单
查单
查成交
入库
异常
停止
```

这些都是回测里不明显、但实盘必须面对的部分。

---

## 23. 当前脚本的学习重点

建议阅读顺序：

1. 先看顶部常量，确认策略参数和回测一致。
2. 再看 `RecursiveCusumReversionFuturesStrategy`，确认 CUSUM、止盈止损、多空反转没有被改坏。
3. 再看 `TestnetOrderExecutionEngine.submit_order()`，理解策略订单如何变成测试网订单。
4. 再看 `sync_account_and_positions()`，理解测试网账户和持仓如何回填到策略对象。
5. 最后看 `main()`，理解实时脚本如何轮询 K 线、驱动策略、写数据库。

核心对照关系是：

```text
回测 BacktestEngine.run()
```

在测试网里被拆成了：

```text
fetch_ohlcv()
process_new_closed_bars()
strategy.on_bar()
TestnetOrderExecutionEngine.submit_order()
sync_account_and_positions()
record_snapshot()
```

---

## 24. 不应该误解的地方

### 24.1 这个脚本不是新的策略

它不是新研发的策略。

它是把已有回测策略迁移到测试网结构中的示范版本。

### 24.2 这个脚本不是主网实盘脚本

它使用测试网和 `sandbox=True`。

主网实盘还需要更严格的风控和异常处理。

### 24.3 `SNAPSHOT_INTERVAL_SECONDS` 不是策略周期

策略周期是：

```python
TIMEFRAME = "5m"
```

轮询间隔是：

```python
SNAPSHOT_INTERVAL_SECONDS = 30
```

### 24.4 测试网账户余额会影响下单量

回测用固定初始资金：

```python
initial_cash=Decimal("10000")
```

测试网使用交易所账户真实可用余额：

```python
strategy.account.available
```

所以同样参数下，测试网下单数量可能和回测不同。

---

## 25. 总结

这个脚本保留了原回测脚本的策略主逻辑：

```text
递归 CUSUM 信号
→ 先止盈止损
→ signal=1 反转到多
→ signal=-1 反转到空
→ available × leverage × position_ratio / price 计算下单数量
```

但把回测环境替换成了测试网环境：

```text
CSV 历史数据 → Binance 测试网 K 线
BacktestEngine 模拟成交 → Binance 测试网真实订单
回测账户 → 测试网账户同步
回测结果对象 → MySQL 运行记录和 dashboard 观察
```

这就是从“逻辑性回测策略”迁移到“测试网策略脚本”时最核心的变化。
