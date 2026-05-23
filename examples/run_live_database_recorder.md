# run_live_database_recorder.py 说明文档

## 作用

`run_live_database_recorder.py` 演示如何单独使用 `LiveDatabaseRecorder` 把实盘或 dry_run 策略状态写入数据库。

这个脚本使用 SQLite 内存数据库和 `DemoClient`，不连接真实交易所，主要用于说明记录器的最小用法。

## 验证链路

```text
SQLite 内存数据库
↓
TradingRepository
↓
MomentumMovingAverageFuturesStrategy
↓
LiveEngine 初始化策略状态
↓
LiveDatabaseRecorder.start_run()
↓
LiveDatabaseRecorder.record_snapshot()
↓
LiveDatabaseRecorder.finish_run()
↓
查询 account_snapshots / position_snapshots / orders
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_live_database_recorder.py
```

## 前置条件

不需要 Binance。

不需要 MySQL。

不需要 API Key。

## 使用的数据库

```text
sqlite:///:memory:
```

脚本结束后数据会消失。

## 输出内容

脚本会打印：

```text
saved run_id
account snapshots
position snapshots
orders
```

## 涉及表

```text
strategy_runs
account_snapshots
position_snapshots
orders
```

## 适合用来验证什么

```text
1. LiveDatabaseRecorder 如何创建 run
2. LiveDatabaseRecorder 如何记录账户快照
3. LiveDatabaseRecorder 如何结束 run
4. TradingRepository 如何读取记录结果
```

## 注意事项

这个脚本只是离线演示，不会真实拉账户余额，也不会真实下单。真实测试网账户记录请看：

```text
run_testnet_account_recorder.py
run_testnet_periodic_live_recorder.py
```
