# run_testnet_order_recorder.py 说明文档

## 作用

`run_testnet_order_recorder.py` 用于验证 Binance Spot Testnet 的订单生命周期记录能力。

它会创建一个远离市价的限价买单，查询订单状态，然后撤单，并把订单状态写入 MySQL 的 `orders` 表。

## 验证链路

```text
Binance Spot Testnet
↓
fetch_ticker()
↓
用市价 80% 创建限价买单
↓
TradingRepository.create_run()
↓
TradingRepository.save_order()
↓
MySQL orders 新增 open 订单
↓
fetch_order()
↓
TradingRepository.update_order_status()
↓
cancel_order()
↓
TradingRepository.update_order_status()
↓
MySQL orders 更新为 canceled
↓
TradingRepository.finish_run()
```

## 默认配置

```text
SYMBOL = BTC/USDT
TARGET_NOTIONAL_USDT = 20
order_price = last_price * 0.8
```

使用低于市价 20% 的限价买单，是为了让订单大概率保持 open，方便验证查询和撤单。

## 运行方式

```bash
cd crypto_quant_framework-main
export BINANCE_TESTNET_API_KEY="你的测试网 Key"
export BINANCE_TESTNET_SECRET_KEY="你的测试网 Secret"
PYTHONPATH=. python examples/run_testnet_order_recorder.py
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
Binance Spot Testnet 订单状态入库完成
symbol
last_price
order_price
amount
exchange_order_id
created_status
fetched_status
canceled_status
run_id
run_type
status
orders
```

## 涉及表

```text
strategy_runs
orders
```

## 是否会成交

正常情况下不会成交，因为买单价格设置为市价的 80%。

## 是否会下单

会在 Binance Spot Testnet 下一个小额限价买单，并马上撤销。

不会使用真实主网资金。

## 适合用来验证什么

```text
1. create_order() 是否可用
2. fetch_order() 是否可用
3. cancel_order() 是否可用
4. orders 表能否保存和更新测试网订单状态
5. strategy_runs 能否记录一次订单测试运行
```

## 注意事项

如果限价单意外成交，说明当时市场价格快速下跌或测试网撮合行为异常。脚本主要目标是验证订单状态，不负责复杂风控。
