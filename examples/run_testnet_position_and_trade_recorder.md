# run_testnet_position_and_trade_recorder.py 说明文档

## 作用

`run_testnet_position_and_trade_recorder.py` 用于一次性验证测试网持仓快照和成交记录入库。

它会在 Binance Spot Testnet 上市价买入小额 BTC，然后记录持仓快照和买入成交，再市价卖出平仓并记录卖出成交。

## 验证链路

```text
Binance Spot Testnet
↓
fetch_ticker()
↓
市价买入 BTC/USDT
↓
TradingRepository.save_order()
↓
MySQL orders 写入买入订单
↓
fetch_balance()
↓
构造 Account / Position
↓
LiveDatabaseRecorder.record_snapshot()
↓
MySQL account_snapshots / position_snapshots
↓
fetch_order_trades()
↓
TradingRepository.save_trade()
↓
MySQL trades 写入买入成交
↓
市价卖出 BTC 平仓
↓
TradingRepository.save_order()
↓
fetch_order_trades()
↓
TradingRepository.save_trade()
↓
MySQL trades 写入卖出成交
↓
LiveDatabaseRecorder.finish_run()
```

## 默认配置

```text
SYMBOL = BTC/USDT
BASE_ASSET = BTC
QUOTE_ASSET = USDT
BUY_NOTIONAL_USDT = 20
```

## 运行方式

```bash
cd crypto_quant_framework-main
export BINANCE_TESTNET_API_KEY="你的测试网 Key"
export BINANCE_TESTNET_SECRET_KEY="你的测试网 Secret"
PYTHONPATH=. python examples/run_testnet_position_and_trade_recorder.py
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

脚本会打印：

```text
Binance Spot Testnet 持仓和成交入库完成
symbol
last_price
buy_amount
buy_order_id
buy_status
buy_filled
sell_order_id
sell_status
sell_filled
run_id
status
orders
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

## 是否会下单

会。

脚本会在 Binance Spot Testnet 上执行：

```text
1. 市价买入小额 BTC
2. 市价卖出同等数量 BTC
```

不会使用真实主网资金。

## 异常处理

如果买入成功但卖出前脚本失败，脚本会尝试卖出已成交数量，避免测试网账户残留本次买入仓位。

## 适合用来验证什么

```text
1. position_snapshots 是否能记录持仓
2. trades 是否能记录真实成交
3. 市价订单 closed 状态是否能保存
4. 买入和平仓流程是否能完整归档
```

## 注意事项

测试网账户本身可能有初始 BTC 余额，所以持仓快照记录的 BTC 数量可能不只包含本次买入数量。
