# run_testnet_account_recorder.py 说明文档

## 作用

`run_testnet_account_recorder.py` 用于验证 OKX Spot Testnet 账户余额能否转换成框架 `Account` 对象，并通过 `LiveDatabaseRecorder` 写入 MySQL 的 `account_snapshots` 表。

## 验证链路

```text
OKX Spot Testnet
↓
fetch_balance()
↓
读取 USDT free / used / total
↓
构造 Account
↓
LiveDatabaseRecorder.start_run()
↓
LiveDatabaseRecorder.record_snapshot()
↓
TradingRepository.save_account_snapshot()
↓
MySQL account_snapshots
↓
LiveDatabaseRecorder.finish_run()
```

## 运行方式

```bash
cd crypto_quant_framework-main
export OKX_DEMO_API_KEY="你的测试网 Key"
export OKX_DEMO_SECRET_KEY="你的测试网 Secret"
PYTHONPATH=. python examples/run_testnet_account_recorder.py
```

运行时会提示输入本地 MySQL 密码。

## 前置条件

需要：

```text
1. 本地 MySQL 正常运行
2. crypto_quant 数据库存在
3. crypto_quant_user 有权限访问数据库
4. OKX Spot Testnet API Key / Secret 已配置到环境变量
5. 本地 SOCKS5 代理 127.0.0.1:1080 可用
```

## 输出内容

脚本会打印：

```text
OKX Spot Testnet 账户快照入库完成
USDT free
USDT used
USDT total
run_id
run_name
run_type
status
final_equity
account_snapshots
```

## 涉及表

```text
strategy_runs
account_snapshots
```

## 是否下单

不会下单。

## 适合用来验证什么

```text
1. 测试网账户余额是否能读取
2. Account 对象是否能正确构造
3. LiveDatabaseRecorder 是否能写账户快照
4. strategy_runs 是否能记录并结束一次测试运行
```

## 注意事项

这个脚本只记录 USDT 账户快照，不记录订单、持仓和成交。后续验证请看：

```text
run_testnet_order_recorder.py
run_testnet_position_and_trade_recorder.py
run_testnet_periodic_live_recorder.py
```
