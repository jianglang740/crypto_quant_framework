# run_testnet_periodic_live_recorder.py 说明文档

## 作用

`run_testnet_periodic_live_recorder.py` 用于模拟更接近实盘运行的周期性数据库记录场景。

它不会修改 `LiveEngine.run()` 主流程，而是在独立脚本中按周期执行账户同步、订单状态同步、成交同步和快照记录，用来测试实盘数据库记录链路的抗压能力。

## 验证链路

```text
Binance Spot Testnet
↓
周期性 fetch_balance()
↓
构造 Account / Position
↓
LiveDatabaseRecorder.record_snapshot()
↓
MySQL account_snapshots / position_snapshots
↓
限价下单 open
↓
TradingRepository.save_order()
↓
TradingRepository.update_order_status()
↓
撤单 canceled
↓
市价买入 closed
↓
fetch_order_trades()
↓
TradingRepository.save_trade()
↓
市价卖出 closed
↓
TradingRepository.save_trade()
↓
LiveDatabaseRecorder.finish_run()
```

## 默认配置

```text
SYMBOL = BTC/USDT
BASE_ASSET = BTC
QUOTE_ASSET = USDT
LIMIT_ORDER_NOTIONAL_USDT = 20
MARKET_BUY_NOTIONAL_USDT = 20
CYCLES = 5
POLL_SECONDS = 3
```

## 模拟场景

脚本分 5 个周期执行：

```text
cycle 1: 同步账户余额并记录快照
cycle 2: 创建远离市价的限价买单并记录 open 状态
cycle 3: 撤销限价单并记录 canceled 状态
cycle 4: 市价买入并写入买入成交和持仓快照
cycle 5: 市价卖出平仓并写入卖出成交
```

## 运行方式

```bash
cd crypto_quant_framework-main
export BINANCE_TESTNET_API_KEY="你的测试网 Key"
export BINANCE_TESTNET_SECRET_KEY="你的测试网 Secret"
PYTHONPATH=. python examples/run_testnet_periodic_live_recorder.py
```

运行时会提示输入本地 MySQL 密码。

## 前置条件

需要：

```text
1. 本地 MySQL 正常运行
2. crypto_quant 数据库存在
3. Binance Spot Testnet API Key / Secret 已配置
4. 本地 SOCKS5 代理 127.0.0.1:1080 可用
5. 测试网账户有足够 USDT
```

## 输出内容

脚本会打印每个周期的进度，以及最终统计：

```text
Binance Spot Testnet 周期性实盘记录压力验证完成
symbol
cycles
last_price
limit_price
limit_order_id
limit_fetched_status
limit_final_status
buy_order_id
buy_status
buy_filled
sell_order_id
sell_status
sell_filled
run_id
status
orders
account_snapshots
position_snapshots
trades
```

## 涉及表

```text
strategy_runs
orders
account_snapshots
position_snapshots
trades
```

## 脚本内去重

脚本使用：

```text
seen_order_ids
seen_trade_ids
```

避免周期同步中重复写入同一订单或同一成交。

## 是否会下单

会。

脚本会在 Binance Spot Testnet 上执行：

```text
1. 低价限价买单
2. 撤销限价买单
3. 市价买入 BTC
4. 市价卖出 BTC
```

不会使用真实主网资金。

## 异常处理

如果脚本中途失败：

```text
1. 如果限价单还没撤销，会尝试撤销
2. 如果市价买入后还没卖出，会尝试卖出已成交数量
3. strategy_runs 会标记为 failed
4. 原始异常会继续抛出，方便排查
```

## 适合用来验证什么

```text
1. 周期性账户快照记录
2. 周期性持仓快照记录
3. open -> canceled 订单状态变化
4. closed 买入 / closed 卖出订单记录
5. 成交记录同步
6. LiveDatabaseRecorder 与 TradingRepository 在连续操作下是否稳定
```

## 注意事项

这不是高频压测脚本，而是“小额、多场景、连续记录”的稳定性验证脚本。

如果要做更长时间 dry_run 验证，可以在此脚本基础上增加周期数、延长间隔、增加日志和异常恢复逻辑。
