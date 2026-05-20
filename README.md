# Crypto Quant Framework

`crypto_quant_framework` 是一个基于 Python、`ccxt` 和 Binance 的加密货币量化交易框架初始版本。框架目标不是直接提供可盈利策略，而是提供一套清晰、可扩展的工程骨架，方便后续继续扩展数据获取、策略开发、回测、实盘交易、数据库存储和绩效分析能力。

当前框架支持：

- Binance 现货交易模式：`spot`
- Binance USD-M 合约交易模式：`future`
- 基于 `ccxt` 的 Binance API 封装
- 类似 backtrader 的数据线思想：`DataFeed` / `DataLine`
- 策略基类：账户、持仓、下单、撤单、平仓、生命周期钩子
- 回测引擎：逐根 K 线推进、模拟成交、权益曲线记录
- 合约回测核心逻辑：杠杆、保证金占用、维持保证金、保证金率、强平价格和强平触发
- CSV 历史数据加载：基于 `pandas` / `numpy` 将本地 OHLCV 文件转换成 `DataFeed`
- 实盘引擎雏形：支持 `dry_run` 模拟下单
- MySQL 数据库层：K线、订单、成交、权益曲线 ORM 模型
- 绩效分析：收益率、最大回撤、夏普、交易次数、胜率等

> 注意：这是一个量化框架骨架，不是投资建议，也不是成熟的生产级交易系统。真实交易前必须充分回测、模拟盘验证、完善风控、日志、异常处理和密钥管理。

- **推荐用户在开始前先阅读一下文档：**

- [📝项目依赖库说明文档](./项目依赖库说明文档.md)
- [🤖StrategyBase说明文档](./StrategyBase说明文档.md)
- [🦃DataFeed说明文档](./DataFeed说明文档.md)
- [🫵BackTest说明文档](./BackTest说明文档.md)


---

## 1. 项目结构

```text
crypto_quant_framework/
├── crypto_quant/
│   ├── __init__.py
│   ├── config.py                 # 配置对象：Binance、MySQL、回测、实盘
│   ├── enums.py                  # 枚举字面量：交易模式、订单方向、订单类型、K线周期等
│   ├── analysis/
│   │   └── performance.py        # 绩效分析
│   ├── data/
│   │   ├── feed.py               # BarData、DataLine、DataFeed
│   │   ├── csv_loader.py         # 基于 pandas/numpy 的 CSV 数据加载
│   │   └── fetcher.py            # 基于 ccxt 的市场数据获取
│   ├── database/
│   │   ├── models.py             # SQLAlchemy ORM 模型
│   │   ├── repository.py         # 数据写入/读取封装
│   │   └── session.py            # MySQL engine/session 创建
│   ├── engine/
│   │   ├── backtest.py           # 回测引擎
│   │   └── live.py               # 实盘引擎雏形
│   ├── exchange/
│   │   └── binance_client.py     # Binance ccxt 客户端封装
│   └── strategy/
│       └── base.py               # 策略基类
├── examples/
│   ├── run_backtest.py           # 回测示例入口
│   ├── run_csv_backtest.py       # 本地 CSV 回测示例入口
│   ├── run_live.py               # 实盘 dry_run 示例入口
│   ├── basic_strategy.py         # 动量 + 均线合约策略示例
│   └── simple_moving_average_strategy.py
├── requirements.txt
└── README.md
```

---

## 2. 环境准备

建议使用 Python 3.11 或更高版本。

### 2.1 进入项目目录

```bash
cd /path/to/crypto_quant_framework
```

例如你下载到 macOS 的 Downloads 目录：

```bash
cd /Users/clinking/Downloads/crypto_quant_framework
```

### 2.2 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

依赖包括：

```text
ccxt
SQLAlchemy
PyMySQL
pandas
numpy
```

其中 `pandas` / `numpy` 主要用于本地 CSV 历史数据加载；如果你使用 conda，也可以按自己的习惯用 conda 安装它们。

### 2.3 运行时导入路径

当前项目还没有打包成标准可编辑安装包，因此运行示例时推荐加上：

```bash
PYTHONPATH=.
```

例如：

```bash
PYTHONPATH=. python3 examples/run_backtest.py
```

如果不加，可能出现：

```text
ModuleNotFoundError: No module named 'crypto_quant'
```

---

## 3. 快速运行第一个回测

在项目根目录执行：

```bash
PYTHONPATH=. python3 examples/run_backtest.py
```

你会看到类似输出：

```text
Account(cash=Decimal('8999.409924'), equity=Decimal('10000.399924'), ...)
PerformanceReport(total_return=Decimal('0.0000399924'), max_drawdown=Decimal('-0.0000380076'), ...)
```

这说明：

- 框架可以正常导入；
- 示例策略可以运行；
- 回测引擎可以驱动策略；
- 绩效分析模块可以输出结果。

当前示例策略只是为了验证框架闭环，不代表真实交易策略。

---

## 4. 推荐阅读顺序

如果你是第一次阅读这个项目，建议按下面顺序理解：

```text
1. examples/run_backtest.py
2. examples/simple_moving_average_strategy.py
3. crypto_quant/strategy/base.py
4. crypto_quant/data/feed.py
5. crypto_quant/engine/backtest.py
6. crypto_quant/config.py
7. crypto_quant/enums.py
8. crypto_quant/exchange/binance_client.py
9. crypto_quant/data/fetcher.py
10. crypto_quant/database/models.py
11. crypto_quant/database/session.py
12. crypto_quant/database/repository.py
13. crypto_quant/engine/live.py
14. crypto_quant/analysis/performance.py
```

最重要的主线是：

```text
数据 DataFeed → 策略 StrategyBase → 回测引擎 BacktestEngine → 绩效 PerformanceAnalyzer
```

---

## 5. 核心概念

### 5.1 BarData：一根 K 线

位置：`crypto_quant/data/feed.py`

```python
@dataclass(frozen=True, slots=True)
class BarData:
    symbol: str
    timeframe: str
    datetime: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
```

每一根 K 线都包含：交易对、周期、时间、开高低收、成交量。

例如：

```python
BarData(
    symbol="BTC/USDT",
    timeframe="1m",
    datetime=datetime(...),
    open=Decimal("100000"),
    high=Decimal("100100"),
    low=Decimal("99900"),
    close=Decimal("100050"),
    volume=Decimal("12.5"),
)
```

### 5.2 DataFeed / DataLine：数据线思想

位置：`crypto_quant/data/feed.py`

`DataFeed` 会把一组 `BarData` 转换成多条数据线：

```python
self.data.open
self.data.high
self.data.low
self.data.close
self.data.volume
self.data.datetime
```

在策略里可以使用：

```python
self.data.close[0]    # 当前 K 线 close
self.data.close[-1]   # 上一根 K 线 close
self.data.high[-2]    # 前两根 K 线 high
```

这类似 backtrader 的 line 设计。

注意：如果历史 K 线数量不足，访问 `[-1]`、`[-2]` 可能越界，需要在策略里自行判断。

### 5.3 StrategyBase：策略基类

位置：`crypto_quant/strategy/base.py`

策略开发主要继承：

```python
StrategyBase
```

常用生命周期方法：

```python
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
```

最重要的是：

```python
on_bar(self, bar)
```

回测或实盘时，每来一根 K 线，就会调用一次 `on_bar()`。

### 5.4 Account：账户对象

位置：`crypto_quant/strategy/base.py`

```python
Account(
    cash=Decimal("10000"),
    equity=Decimal("10000"),
    available=Decimal("10000"),
    margin=Decimal("0"),
    realized_pnl=Decimal("0"),
    unrealized_pnl=Decimal("0"),
)
```

字段含义：

| 字段 | 含义 |
|---|---|
| `cash` | 现金余额 |
| `equity` | 总权益 |
| `available` | 可用资金 |
| `margin` | 合约已占用保证金 |
| `maintenance_margin` | 维持保证金 |
| `margin_ratio` | 保证金率，当前简化为 `maintenance_margin / equity` |
| `realized_pnl` | 已实现盈亏 |
| `unrealized_pnl` | 未实现盈亏 |

### 5.5 Position：持仓对象

```python
Position(
    symbol="BTC/USDT",
    side=PositionSide.BOTH,
    amount=Decimal("0.01"),
    entry_price=Decimal("100000"),
    mark_price=Decimal("100100"),
    unrealized_pnl=Decimal("1"),
)
```

常用方法：

```python
position = self.get_position("BTC/USDT")

if position.is_flat:
    ...
```

### 5.6 下单方法

在策略里可以直接调用：

```python
self.buy("BTC/USDT", Decimal("0.01"))
self.sell("BTC/USDT", Decimal("0.01"))
self.close_position("BTC/USDT")
```

合约做空相关：

```python
self.short("BTC/USDT", Decimal("0.01"))
self.cover("BTC/USDT", Decimal("0.01"))
```

限价单示例：

```python
self.buy("BTC/USDT", Decimal("0.01"), price=Decimal("95000"))
```

如果不传 `price`，默认是市价单；如果传了 `price`，默认是限价单。

---

## 6. 写一个自己的策略

新建文件：

```text
examples/my_strategy.py
```

示例：连续 3 根阳线买入，连续 2 根阴线平仓。

```python
from collections import deque
from decimal import Decimal

from crypto_quant.data import BarData
from crypto_quant.strategy import StrategyBase


class MyStrategy(StrategyBase):
    name = "my_strategy"

    def __init__(self):
        super().__init__()
        self.last_bars: deque[BarData] = deque(maxlen=3)

    def on_bar(self, bar: BarData) -> None:
        self.last_bars.append(bar)
        if len(self.last_bars) < 3:
            return

        position = self.get_position(bar.symbol)
        bars = list(self.last_bars)

        three_bullish = all(item.close > item.open for item in bars)
        two_bearish = bars[-1].close < bars[-1].open and bars[-2].close < bars[-2].open

        if three_bullish and position.is_flat:
            self.buy(bar.symbol, Decimal("0.01"))
        elif two_bearish and not position.is_flat:
            self.close_position(bar.symbol)
```

然后在 `examples/run_backtest.py` 中把策略替换成：

```python
from examples.my_strategy import MyStrategy

strategy = MyStrategy()
```

再运行：

```bash
PYTHONPATH=. python3 examples/run_backtest.py
```

---

## 7. 回测引擎说明

位置：`crypto_quant/engine/backtest.py`

核心用法：

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

result = engine.run(strategy, data)
```

`BacktestConfig` 字段：

| 字段 | 默认值 | 含义 |
|---|---:|---|
| `initial_cash` | `10000` | 初始资金 |
| `commission_rate` | `0.0004` | 手续费率 |
| `slippage_rate` | `0` | 滑点率 |
| `allow_short` | `True` | 是否允许做空，当前版本预留 |
| `leverage` | `1` | 合约杠杆倍数 |
| `margin_mode` | `CROSS` | 合约保证金模式配置，目前主要作为配置字段保留 |
| `maintenance_margin_rate` | `0.005` | 维持保证金率，用于计算强平触发条件 |
| `liquidation_fee_rate` | `0.001` | 强平手续费率 |

`BacktestResult` 包含：

```python
result.trades          # 成交列表
result.equity_curve    # 权益曲线
result.final_account   # 最终账户
result.orders          # 订单列表
```

当前回测撮合逻辑是简化版：

- 市价单按当前 bar 的 close 成交；
- 限价买单价格低于当前 bar low 时不成交；
- 限价卖单价格高于当前 bar high 时不成交；
- 手续费按 `notional * commission_rate` 计算；
- 滑点按 `price * slippage_rate` 计算。

合约模式下，回测引擎还会额外处理：

- 开仓保证金占用：`notional / leverage`；
- 平仓释放保证金；
- 多头/空头已实现盈亏和未实现盈亏；
- 账户权益：`cash + unrealized_pnl`；
- 可用资金：`equity - margin`；
- 维持保证金：`mark_price * abs(amount) * maintenance_margin_rate`；
- 当 `equity <= maintenance_margin` 时触发简化强平。

---

## 8. 本地 CSV 回测

如果你已经有本地历史 K 线 CSV，可以使用 `load_bars_from_csv()` 转成框架需要的 `DataFeed`。

CSV 至少需要包含这些列：

```text
datetime, open, high, low, close
```

`volume` 是可选列；如果没有，框架会自动填 0。

示例：

```python
from crypto_quant.data import load_bars_from_csv

data = load_bars_from_csv(
    path="data/ETH_USDT_USDT_15m.csv",
    symbol="ETH/USDT",
    timeframe="15m",
)
```

也可以直接运行示例入口：

```bash
PYTHONPATH=. python3 examples/run_csv_backtest.py
```

`symbol` 和 `timeframe` 由你手动传入，是因为很多 CSV 只保存 OHLCV 数据，不一定在文件内容里写明交易对和周期。

---

## 9. 绩效分析

位置：`crypto_quant/analysis/performance.py`

用法：

```python
from crypto_quant.analysis import PerformanceAnalyzer

report = PerformanceAnalyzer().analyze(
    result.equity_curve,
    result.trades,
)

print(report)
```

输出对象：`PerformanceReport`

| 字段 | 含义 |
|---|---|
| `total_return` | 总收益率 |
| `max_drawdown` | 最大回撤 |
| `sharpe_ratio` | 夏普比率 |
| `trade_count` | 交易次数 |
| `win_rate` | 胜率 |
| `gross_profit` | 总盈利 |
| `gross_loss` | 总亏损 |

当前绩效分析也是简化版，后续可以扩展：

- 年化收益率
- Calmar Ratio
- Sortino Ratio
- 按日/周/月收益统计
- 单笔交易明细归因
- 多空分开统计
- 手续费与滑点分析

---

## 10. Binance 数据获取

位置：`crypto_quant/data/fetcher.py`

### 9.1 创建 Binance 客户端

```python
from crypto_quant.config import BinanceConfig
from crypto_quant.enums import TradingMode
from crypto_quant.exchange import BinanceClient

client = BinanceClient(
    BinanceConfig(
        trading_mode=TradingMode.SPOT,
        sandbox=False,
    )
)
```

如果是合约：

```python
client = BinanceClient(
    BinanceConfig(
        trading_mode=TradingMode.FUTURE,
        sandbox=False,
    )
)
```

### 9.2 获取 K 线

```python
from crypto_quant.data import DataFeed, MarketDataFetcher
from crypto_quant.enums import KlineInterval

fetcher = MarketDataFetcher(client)

bars = fetcher.fetch_ohlcv(
    symbol="BTC/USDT",
    timeframe=KlineInterval.M1,
    limit=500,
)

data = DataFeed(bars)
```

### 9.3 支持的数据方法

```python
fetcher.fetch_ohlcv(...)
fetcher.fetch_ticker(...)
fetcher.fetch_tickers(...)
fetcher.fetch_order_book(...)
fetcher.fetch_trades(...)
fetcher.fetch_funding_rate(...)
fetcher.fetch_funding_rate_history(...)
```

---

## 11. Binance 交易封装

位置：`crypto_quant/exchange/binance_client.py`

### 10.1 现货模式

```python
from crypto_quant.config import BinanceConfig
from crypto_quant.enums import TradingMode
from crypto_quant.exchange import BinanceClient

client = BinanceClient(
    BinanceConfig(
        api_key="你的 API KEY",
        secret="你的 SECRET",
        trading_mode=TradingMode.SPOT,
        sandbox=True,
    )
)
```

### 10.2 合约模式

```python
client = BinanceClient(
    BinanceConfig(
        api_key="你的 API KEY",
        secret="你的 SECRET",
        trading_mode=TradingMode.FUTURE,
        sandbox=True,
    )
)
```

合约模式会设置：

```python
options={"defaultType": "future"}
```

即 Binance USD-M futures。

### 10.3 常用方法

```python
client.load_markets()
client.fetch_balance()
client.fetch_positions(["BTC/USDT"])
client.set_leverage("BTC/USDT", 3)
client.set_margin_mode("BTC/USDT", MarginMode.CROSS)
client.create_order(...)
client.cancel_order(order_id, "BTC/USDT")
client.fetch_order(order_id, "BTC/USDT")
client.fetch_open_orders("BTC/USDT")
client.close_position("BTC/USDT", amount=0.01)
```

---

## 12. 实盘引擎 dry_run 示例

位置：`crypto_quant/engine/live.py` 和 `examples/run_live.py`

当前实盘引擎是初始版本，建议先只使用 `dry_run=True`。

```python
from crypto_quant.config import LiveConfig
from crypto_quant.engine import LiveEngine

engine = LiveEngine(
    client,
    LiveConfig(
        dry_run=True,
        poll_interval_seconds=10,
    ),
)
```

`dry_run=True` 时：

- 策略可以正常发出订单；
- 系统会生成本地 dry-run 订单；
- 不会向 Binance 真实下单。

只有当你充分确认策略、风控、日志、异常处理都没问题后，才考虑改成：

```python
dry_run=False
```

真实交易前建议至少补充：

- API key 从环境变量读取，不能写死在代码里；
- 最大单笔下单金额限制；
- 最大持仓限制；
- 每日最大亏损限制；
- 网络异常重试与熔断；
- 订单状态轮询与撤单逻辑；
- 实盘日志记录；
- Telegram/邮件告警；
- 测试网验证。

---

## 13. MySQL 数据库层

位置：

```text
crypto_quant/database/models.py
crypto_quant/database/session.py
crypto_quant/database/repository.py
```

### 12.1 数据表

当前定义了 4 类 ORM 模型：

| 模型 | 表名 | 用途 |
|---|---|---|
| `Kline` | `klines` | K线数据 |
| `OrderRecord` | `orders` | 订单记录 |
| `TradeRecord` | `trades` | 成交记录 |
| `EquityCurve` | `equity_curve` | 权益曲线 |

### 12.2 初始化数据库表

先在 MySQL 中创建数据库：

```sql
CREATE DATABASE crypto_quant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后执行：

```python
from crypto_quant.config import MySQLConfig
from crypto_quant.database import Base, create_mysql_engine

engine = create_mysql_engine(
    MySQLConfig(
        host="127.0.0.1",
        port=3306,
        username="root",
        password="你的密码",
        database="crypto_quant",
    )
)

Base.metadata.create_all(engine)
```

### 12.3 保存 K 线

```python
from crypto_quant.database import create_session_factory
from crypto_quant.database.repository import MarketDataRepository

SessionFactory = create_session_factory(engine)

with SessionFactory() as session:
    repo = MarketDataRepository(session)
    repo.upsert_klines(bars)
```

---

## 14. 枚举与 Binance 字面量

位置：`crypto_quant/enums.py`

### 13.1 交易模式

```python
TradingMode.SPOT    # "spot"
TradingMode.FUTURE  # "future"
```

### 13.2 订单方向

```python
OrderSide.BUY   # "buy"
OrderSide.SELL  # "sell"
```

### 13.3 订单类型

```python
OrderType.MARKET
OrderType.LIMIT
OrderType.STOP
OrderType.STOP_MARKET
OrderType.TAKE_PROFIT
OrderType.TAKE_PROFIT_MARKET
OrderType.TRAILING_STOP_MARKET
```

### 13.4 K线周期

```python
KlineInterval.M1    # "1m"
KlineInterval.M5    # "5m"
KlineInterval.H1    # "1h"
KlineInterval.D1    # "1d"
KlineInterval.W1    # "1w"
KlineInterval.MN1   # "1M"
```

---

## 15. 常见问题

### 14.1 ModuleNotFoundError: No module named 'crypto_quant'

原因：没有从项目根目录运行，或者没有设置 `PYTHONPATH`。

解决：

```bash
cd /path/to/crypto_quant_framework
PYTHONPATH=. python3 examples/run_backtest.py
```

### 14.2 ModuleNotFoundError: No module named 'ccxt'

原因：依赖没安装。

解决：

```bash
python3 -m pip install -r requirements.txt
```

### 14.3 为什么示例回测只有 1 笔交易？

当前示例数据是手工构造的单边上涨数据，示例均线策略主要用于验证框架能跑通，不保证产生完整买卖闭环。

你可以修改：

```text
examples/run_backtest.py
examples/simple_moving_average_strategy.py
```

构造更复杂的数据，或者接入 Binance 历史 K 线。

### 14.4 可以直接真实下单吗？

不建议。当前框架是初始骨架，真实交易前至少需要补充风控、日志、异常处理、订单状态同步和测试网验证。

实盘阶段建议先使用：

```python
LiveConfig(dry_run=True)
```

---

## 16. 后续开发建议

建议按下面路线逐步完善：

### 阶段 1：工程化完善

- 增加 `pyproject.toml`，支持 `pip install -e .`
- 增加 `.gitignore`
- 增加单元测试目录 `tests/`
- 增加日志模块
- 增加 `.env` 配置读取

### 阶段 2：数据能力

- 支持批量拉取历史 K 线
- 支持自动存入 MySQL
- 支持从 MySQL 读取历史数据回测
- 支持多交易对、多周期数据

### 阶段 3：回测能力

- 更精细的订单撮合
- 多标的组合回测
- 更贴近交易所真实规则的合约保证金、资金费率和阶梯维持保证金模型
- funding fee 模拟
- 手续费等级配置
- 止盈止损单模拟

### 阶段 4：策略能力

- 策略参数管理
- 批量参数优化
- 多策略组合
- 信号与执行分离
- 风控模块

### 阶段 5：实盘能力

- API key 环境变量管理
- 订单状态轮询
- 异常重试与熔断
- 交易日志落库
- 账户和持仓同步
- 实盘告警

---

## 17. 最小开发闭环

日常开发可以按这个流程：

```text
1. 在 examples/ 下写策略
2. 用 DataFeed 准备数据
3. 用 BacktestEngine 跑回测
4. 用 PerformanceAnalyzer 看绩效
5. 调整策略参数
6. 回测稳定后再考虑 dry_run 实盘
```

示例代码：

```python
from decimal import Decimal

from crypto_quant.analysis import PerformanceAnalyzer
from crypto_quant.config import BacktestConfig
from crypto_quant.data import DataFeed
from crypto_quant.engine import BacktestEngine
from examples.simple_moving_average_strategy import SimpleMovingAverageStrategy

strategy = SimpleMovingAverageStrategy()
engine = BacktestEngine(
    BacktestConfig(initial_cash=Decimal("10000"))
)

result = engine.run(strategy, DataFeed(bars))
report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)

print(result.final_account)
print(report)
```

---

## 18. 风险提示

加密货币交易风险极高，尤其是合约交易。使用本框架进行真实交易前，请务必确认：

- 你理解代码的每一处下单逻辑；
- 你已经完成足够长周期的历史回测；
- 你已经完成模拟盘验证；
- 你设置了最大亏损、最大仓位、最大杠杆等风控；
- 你不会把 API key、secret 提交到 GitHub；
- 你能接受策略失效、网络异常、交易所异常和极端行情带来的损失。
