# `crypto_quant/database` 数据库模块说明文档

本文档详细解释 `crypto_quant/database` 数据库模块的设计目的、文件结构、MySQL 使用方式、表结构、字段含义、仓库方法，以及它和回测、实盘、行情数据之间的关系。

当前项目正式设计的数据库是：

```text
MySQL + PyMySQL + SQLAlchemy
```

示例或测试中有时会使用 SQLite 内存数据库，这是为了方便快速验证 ORM 和 repository 逻辑，不代表项目目标数据库改成 SQLite。

---

## 1. 数据库模块整体定位

数据库模块位置：

```text
crypto_quant/database/
```

它的作用是把框架运行过程中产生的数据保存到 MySQL 中，包括：

```text
1. 历史 K 线数据；
2. 回测运行批次；
3. 回测订单；
4. 回测成交；
5. 回测权益曲线；
6. 实盘账户快照；
7. 实盘持仓快照；
8. 实盘订单状态。
```

在整个框架中的位置可以理解为：

```text
行情数据 / 回测结果 / 实盘状态
              ↓
        database repository
              ↓
             MySQL
```

现在数据库模块不会强制接入回测或实盘引擎主流程，而是提供 repository 方法让你主动调用。

这样做的好处是：

```text
1. 不破坏现有回测和实盘引擎代码；
2. 不强制所有使用者都必须配置数据库；
3. 需要保存时再调用 repository；
4. 数据库层可以先独立完善。
```

---

## 2. 文件结构

当前数据库模块包含：

```text
crypto_quant/database/
├── __init__.py
├── models.py
├── repository.py
└── session.py
```

| 文件 | 作用 |
|---|---|
| `models.py` | 定义 SQLAlchemy ORM 表模型，也就是 MySQL 表结构 |
| `repository.py` | 封装写入和查询方法，避免业务代码直接写 SQL |
| `session.py` | 创建 MySQL engine、session factory、建表工具和事务上下文 |
| `__init__.py` | 对外导出常用模型、repository 和工具函数 |

---

## 3. MySQL 配置

MySQL 配置类在：

```text
crypto_quant/config.py
```

配置对象：

```python
@dataclass(slots=True)
class MySQLConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    username: str = "root"
    password: str = ""
    database: str = "crypto_quant"
    charset: str = "utf8mb4"
    echo: bool = False
```

字段说明：

| 字段 | 中文说明 |
|---|---|
| `host` | MySQL 主机地址，默认是本机 `127.0.0.1` |
| `port` | MySQL 端口，默认是 `3306` |
| `username` | MySQL 用户名，默认是 `root` |
| `password` | MySQL 密码 |
| `database` | 要连接的数据库名，默认是 `crypto_quant` |
| `charset` | 字符集，默认是 `utf8mb4`，适合中文和 emoji |
| `echo` | 是否打印 SQLAlchemy 执行的 SQL，调试时可以设为 `True` |

最终连接 URL 格式是：

```text
mysql+pymysql://用户名:密码@主机:端口/数据库名?charset=utf8mb4
```

---

## 4. session 工具

文件：

```text
crypto_quant/database/session.py
```

### 4.1 创建 MySQL engine

```python
def create_mysql_engine(config: MySQLConfig) -> Engine:
```

作用：根据 `MySQLConfig` 创建 SQLAlchemy engine。

内部使用：

```python
pool_pre_ping=True
```

这可以减少 MySQL 长连接闲置后断开导致的错误。

### 4.2 创建 session factory

```python
def create_session_factory(engine: Engine) -> Callable[[], Session]:
```

作用：创建 session 工厂。

以后可以通过：

```python
Session = create_session_factory(engine)
session = Session()
```

拿到数据库 session。

### 4.3 创建所有表

```python
def create_all_tables(engine: Engine) -> None:
```

作用：调用：

```python
Base.metadata.create_all(engine)
```

根据 ORM 模型创建 MySQL 表。

注意：

```text
create_all_tables 适合第一版初始化数据库。
如果以后项目进入更正式阶段，建议使用 Alembic 做数据库迁移。
```

### 4.4 事务上下文

```python
def session_scope(session_factory):
```

作用：提供自动 commit / rollback / close 的上下文管理器。

示例：

```python
with session_scope(Session) as session:
    repo = TradingRepository(session)
    repo.create_run(...)
```

如果代码正常执行，会自动提交。

如果中间出错，会自动 rollback。

---

## 5. ORM 表结构总览

当前一共有 7 张主要表：

| 表名 | ORM 类 | 作用 |
|---|---|---|
| `strategy_runs` | `StrategyRun` | 保存一次回测、组合回测、dry_run 或实盘运行记录 |
| `klines` | `Kline` | 保存历史 K 线数据 |
| `orders` | `OrderRecord` | 保存订单记录 |
| `trades` | `TradeRecord` | 保存成交记录 |
| `equity_curve` | `EquityCurve` | 保存权益曲线 |
| `account_snapshots` | `AccountSnapshot` | 保存账户快照 |
| `position_snapshots` | `PositionSnapshot` | 保存持仓快照 |

这些表之间主要通过：

```text
run_id
```

进行关联。

可以理解为：

```text
strategy_runs.run_id
      ↓
orders.run_id
trades.run_id
equity_curve.run_id
account_snapshots.run_id
position_snapshots.run_id
```

---

## 6. `strategy_runs`：策略运行批次表

ORM 类：

```python
StrategyRun
```

表名：

```text
strategy_runs
```

作用：记录一次完整运行。

一次运行可以是：

```text
单策略回测
多策略组合回测
dry_run 模拟实盘
真实实盘
```

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键，只用于 MySQL 内部识别 |
| `run_id` | 一次运行的唯一编号，用来关联订单、成交、权益、账户快照和持仓快照 |
| `name` | 本次运行名称，例如 `database_demo_backtest` |
| `run_type` | 运行类型，例如 `backtest`、`portfolio_backtest`、`dry_run`、`live` |
| `trading_mode` | 交易模式，例如 `spot` 或 `future` |
| `strategy_name` | 策略名称，单策略时保存策略名，组合回测时可以保存组合名称或主名称 |
| `symbols` | 本次运行涉及的交易对列表，使用 JSON 字符串保存 |
| `timeframe` | 本次运行主要使用的 K 线周期，例如 `1m`、`15m`、`1h` |
| `started_at` | 运行开始时间 |
| `ended_at` | 运行结束时间，未结束时为空 |
| `initial_cash` | 初始资金 |
| `final_equity` | 结束时最终权益 |
| `status` | 运行状态，例如 `running`、`finished`、`failed` |
| `config` | 本次运行配置快照，使用 JSON 字符串保存 |
| `created_at` | 记录创建时间 |

---

## 7. `klines`：K 线表

ORM 类：

```python
Kline
```

表名：

```text
klines
```

作用：保存历史行情 K 线。

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键 |
| `exchange` | 交易所名称，默认是 `binance` |
| `symbol` | 交易对，例如 `BTC/USDT`、`ETH/USDT` |
| `timeframe` | K 线周期，例如 `1m`、`15m`、`1h` |
| `open_time` | K 线开始时间 |
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `volume` | 成交量 |

唯一索引：

```text
exchange + symbol + timeframe + open_time
```

含义是：

```text
同一个交易所、同一个交易对、同一个周期、同一个时间点，只能有一条 K 线。
```

这方便做 MySQL upsert：如果 K 线已存在就更新，不存在就插入。

---

## 8. `orders`：订单表

ORM 类：

```python
OrderRecord
```

表名：

```text
orders
```

作用：保存回测或实盘订单。

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键 |
| `run_id` | 所属运行编号，对应 `strategy_runs.run_id` |
| `strategy_name` | 产生该订单的策略名称 |
| `exchange` | 交易所名称，默认是 `binance` |
| `exchange_order_id` | 交易所订单 ID，真实实盘订单通常会有这个值 |
| `client_order_id` | 本地订单 ID，回测或本地订单通常使用这个值 |
| `symbol` | 交易对，例如 `BTC/USDT` |
| `trading_mode` | 交易模式，例如 `spot` 或 `future` |
| `side` | 买卖方向，例如 `buy` 或 `sell` |
| `order_type` | 订单类型，例如 `market`、`limit` |
| `status` | 订单状态，例如 `open`、`closed`、`canceled`、`rejected` |
| `amount` | 下单数量 |
| `price` | 下单价格，市价单可以为空 |
| `filled` | 已成交数量 |
| `average` | 平均成交价格 |
| `position_side` | 合约持仓方向，例如 `LONG`、`SHORT`、`BOTH` |
| `reduce_only` | 是否只减仓，合约平仓时常用 |
| `time_in_force` | 订单有效方式，例如 `GTC`、`IOC`、`FOK` |
| `raw` | 原始订单数据 JSON，用于排查和复盘 |
| `created_at` | 订单创建时间 |
| `updated_at` | 订单最后更新时间 |

---

## 9. `trades`：成交表

ORM 类：

```python
TradeRecord
```

表名：

```text
trades
```

作用：保存成交记录。

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键 |
| `run_id` | 所属运行编号，对应 `strategy_runs.run_id` |
| `strategy_name` | 产生该成交的策略名称 |
| `exchange` | 交易所名称，默认是 `binance` |
| `exchange_trade_id` | 交易所成交 ID，回测中可以保存本地成交 ID |
| `exchange_order_id` | 该成交所属的交易所订单 ID |
| `trading_mode` | 交易模式，例如 `spot` 或 `future` |
| `symbol` | 交易对，例如 `BTC/USDT` |
| `side` | 成交方向，例如 `buy` 或 `sell` |
| `position_side` | 合约持仓方向，例如 `LONG`、`SHORT`、`BOTH` |
| `amount` | 成交数量 |
| `price` | 成交价格 |
| `fee` | 手续费金额 |
| `fee_asset` | 手续费币种，例如 `USDT`、`BNB` |
| `realized_pnl` | 已实现盈亏，当前字段预留给后续更精确统计 |
| `traded_at` | 成交时间 |
| `raw` | 原始成交数据 JSON |
| `created_at` | 记录创建时间 |

---

## 10. `equity_curve`：权益曲线表

ORM 类：

```python
EquityCurve
```

表名：

```text
equity_curve
```

作用：保存账户权益随时间变化的曲线。

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键 |
| `run_id` | 所属运行编号，对应 `strategy_runs.run_id` |
| `strategy_name` | 策略名称 |
| `trading_mode` | 交易模式，例如 `spot` 或 `future` |
| `timestamp` | 权益点对应的时间 |
| `cash` | 现金余额 |
| `equity` | 账户总权益 |
| `available` | 可用余额 |
| `margin` | 当前占用保证金 |
| `maintenance_margin` | 维持保证金 |
| `realized_pnl` | 已实现盈亏 |
| `unrealized_pnl` | 未实现盈亏 |

注意：

```text
当前 BacktestResult 的 equity_curve 只有 timestamp + equity。
所以保存回测结果时，equity 是每个时间点的值，其他账户字段主要来自 final_account。
如果以后想保存每个时间点完整账户状态，需要增强回测引擎的 account curve。
```

---

## 11. `account_snapshots`：账户快照表

ORM 类：

```python
AccountSnapshot
```

表名：

```text
account_snapshots
```

作用：保存某一时刻的账户状态，主要用于实盘或 dry_run 定期记录。

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键 |
| `run_id` | 所属运行编号，对应 `strategy_runs.run_id` |
| `timestamp` | 快照时间 |
| `trading_mode` | 交易模式，例如 `spot` 或 `future` |
| `cash` | 现金余额 |
| `equity` | 账户总权益 |
| `available` | 可用余额 |
| `margin` | 当前占用保证金 |
| `maintenance_margin` | 维持保证金 |
| `margin_ratio` | 保证金率，用于衡量账户风险 |
| `realized_pnl` | 已实现盈亏 |
| `unrealized_pnl` | 未实现盈亏 |
| `raw` | 原始账户数据 JSON，真实实盘同步时可保存交易所原始响应 |

---

## 12. `position_snapshots`：持仓快照表

ORM 类：

```python
PositionSnapshot
```

表名：

```text
position_snapshots
```

作用：保存某一时刻的持仓状态。

字段说明：

| 字段 | 中文说明 |
|---|---|
| `id` | 数据库自增主键 |
| `run_id` | 所属运行编号，对应 `strategy_runs.run_id` |
| `strategy_name` | 策略名称 |
| `timestamp` | 快照时间 |
| `symbol` | 交易对，例如 `BTC/USDT` |
| `side` | 持仓方向，例如 `LONG`、`SHORT`、`BOTH` |
| `amount` | 持仓数量 |
| `entry_price` | 平均开仓价格 |
| `mark_price` | 标记价格或当前估值价格 |
| `margin` | 当前仓位占用保证金 |
| `liquidation_price` | 预估强平价格，现货或无强平价时为空 |
| `unrealized_pnl` | 未实现盈亏 |
| `raw` | 原始持仓数据 JSON，真实实盘同步时可保存交易所原始响应 |

---

## 13. `MarketDataRepository` 方法

### 13.1 写入 K 线

```python
upsert_klines(bars, exchange="binance")
```

作用：把 `BarData` 列表写入 `klines` 表。

它使用 MySQL 的：

```text
ON DUPLICATE KEY UPDATE
```

如果 K 线已存在，就更新 OHLCV；如果不存在，就插入。

### 13.2 查询 K 线

```python
get_klines(symbol, timeframe, start=None, end=None, exchange="binance", limit=None)
```

作用：从 MySQL 查询 K 线。

支持按：

```text
交易所
交易对
周期
开始时间
结束时间
数量限制
```

过滤。

### 13.3 恢复成 DataFeed

```python
get_data_feed(...)
```

作用：

```text
MySQL Kline
    ↓
BarData
    ↓
DataFeed
```

这样数据库里的 K 线可以直接进入回测引擎。

---

## 14. `TradingRepository` 写入方法

主要写入方法包括：

| 方法 | 中文说明 |
|---|---|
| `create_run()` | 创建一次运行记录 |
| `finish_run()` | 标记一次运行结束 |
| `save_order()` | 保存 ccxt / Binance 返回的订单 dict |
| `save_local_order()` | 保存框架内部 `LocalOrder` |
| `upsert_local_order()` | 插入或更新框架内部 `LocalOrder` |
| `update_order_status()` | 按订单 ID 更新订单状态 |
| `save_framework_trade()` | 保存框架内部 `Trade` |
| `save_equity_point()` | 保存一个权益点 |
| `save_account_snapshot()` | 保存账户快照 |
| `save_position_snapshot()` | 保存持仓快照 |
| `save_live_snapshot()` | 保存当前策略账户、持仓和订单状态 |
| `save_backtest_result()` | 保存单策略或组合回测结果 |

---

## 15. `TradingRepository` 查询方法

当前查询方法包括：

| 方法 | 中文说明 |
|---|---|
| `get_run(run_id)` | 根据运行编号查询一次运行 |
| `list_runs()` | 查询运行记录列表，可按类型、策略名、状态过滤 |
| `get_orders(run_id)` | 查询某次运行的订单 |
| `get_trades(run_id)` | 查询某次运行的成交 |
| `get_equity_curve(run_id)` | 查询某次运行的权益曲线 |
| `get_account_snapshots(run_id)` | 查询某次运行的账户快照 |
| `get_position_snapshots(run_id)` | 查询某次运行的持仓快照 |

这些查询方法让数据库模块不仅能写入结果，也能把结果读出来做复盘。

---

## 16. 示例：创建 MySQL 表

```python
from crypto_quant.config import MySQLConfig
from crypto_quant.database import create_all_tables, create_mysql_engine

config = MySQLConfig(
    host="127.0.0.1",
    port=3306,
    username="root",
    password="你的密码",
    database="crypto_quant",
)

engine = create_mysql_engine(config)
create_all_tables(engine)
```

执行后，会根据 ORM 模型在 MySQL 中创建表。

---

## 17. 示例：从 MySQL 读取 K 线回测

```python
from crypto_quant.database import MarketDataRepository
from crypto_quant.engine.backtest import BacktestEngine

market_repo = MarketDataRepository(session)
data = market_repo.get_data_feed("BTC/USDT", "1m")

engine = BacktestEngine()
result = engine.run(strategy, data)
```

流程是：

```text
MySQL klines
    ↓
get_data_feed
    ↓
DataFeed
    ↓
BacktestEngine
```

---

## 18. 示例：保存回测结果

```python
from crypto_quant.database import TradingRepository
from crypto_quant.enums import TradingMode

trading_repo = TradingRepository(session)
run = trading_repo.save_backtest_result(
    result,
    strategy_name=strategy.name,
    trading_mode=TradingMode.FUTURE.value,
    run_name="my_backtest",
)
```

它会保存：

```text
strategy_runs
orders
trades
equity_curve
```

然后可以查询：

```python
orders = trading_repo.get_orders(run.run_id)
trades = trading_repo.get_trades(run.run_id)
equity_curve = trading_repo.get_equity_curve(run.run_id)
```

---

## 19. 示例：保存实盘快照

```python
run = trading_repo.create_run(
    name="live_btc_strategy",
    run_type="live",
    trading_mode=strategy.trading_mode.value,
    strategy_name=strategy.name,
)

trading_repo.save_live_snapshot(strategy, run.run_id)
```

它会保存：

```text
账户快照
非空持仓快照
当前订单状态
```

其中订单使用 `upsert_local_order()`，所以同一个 `run_id + client_order_id` 下不会不断插入重复订单，而是更新已有订单状态。

---

## 20. 实盘数据库记录器

现在数据库模块新增了独立记录器：

```python
from crypto_quant.database import LiveDatabaseRecorder
```

它的定位是：

```text
不修改 LiveEngine.run() 主流程，
只提供一个可选组件，
让用户在实盘循环外部主动记录数据库。
```

基本用法：

```python
recorder = LiveDatabaseRecorder(trading_repo, run_name="my_live_run")
run = recorder.start_run(strategy, symbols=["BTC/USDT"])
recorder.record_snapshot(strategy)
recorder.record_orders(strategy)
recorder.finish_run(strategy)
```

它会使用现有 repository 保存：

```text
1. strategy_runs 运行批次；
2. account_snapshots 账户快照；
3. position_snapshots 非空持仓快照；
4. orders 当前订单状态。
```

其中订单使用 `upsert_local_order()`，所以同一个运行批次里的同一个本地订单不会重复插入。

---

## 21. 数据库回测示例脚本

示例文件：

```text
examples/run_database_backtest.py
```

这个示例演示：

```text
1. 创建临时数据库；
2. 创建表；
3. 写入演示 K 线；
4. 从数据库恢复 DataFeed；
5. 运行回测；
6. 保存回测结果；
7. 查询 run、orders、trades、equity_curve。
```

运行：

```bash
PYTHONPATH=. python3 examples/run_database_backtest.py
```

注意：

```text
这个示例默认使用 SQLite 内存数据库，只是为了让示例不用配置 MySQL 也能快速运行。
项目正式数据库仍然是 MySQL。
```

---

## 22. 当前边界

当前数据库模块已经可以作为第一版持久化层使用，但仍然有一些边界：

```text
1. 还没有自动接入 BacktestEngine / PortfolioBacktestEngine / LiveEngine 主流程；
2. 还没有 Alembic 迁移；
3. 回测权益曲线当前只有每个时间点的 equity 最准确，其他账户字段来自 final_account；
4. 实盘订单对账还没有完整自动化；
5. 真实成交同步成 TradeRecord 的流程还可以继续增强；
6. 查询方法目前是基础查询，还没有复杂统计和报表接口；
7. K 线 upsert 使用 MySQL 专用语法，SQLite 只适合做临时测试。
```

---

## 23. 后续可以继续增强的方向

后续可以继续扩展：

```text
1. Alembic 数据库迁移；
2. 回测引擎记录完整 account curve；
3. LiveEngine 可选数据库记录器；
4. 订单状态自动对账；
5. 成交自动同步；
6. 数据库层绩效查询；
7. 多策略组合归因查询；
8. 按 symbol / strategy / run_type 做历史表现统计；
9. 实盘风控日志表；
10. 报表查询接口。
```

---

## 24. 一句话总结

```text
crypto_quant/database 的作用是：
把行情、回测结果、实盘状态保存到 MySQL，并提供读取和复盘入口。
```

现在它已经支持：

```text
K 线入库和读取；
DataFeed 恢复；
回测结果保存；
组合回测结果保存；
实盘账户和持仓快照保存；
订单状态更新；
基础查询复盘。
```
