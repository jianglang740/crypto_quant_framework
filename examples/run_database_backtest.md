# run_database_backtest.py 说明文档

## 作用

`run_database_backtest.py` 演示如何把行情写入数据库，再从数据库读回 `DataFeed`，运行回测，并把回测结果保存回数据库。

这个脚本使用 SQLite 内存数据库，主要用于离线演示数据库闭环，不依赖本地 MySQL。

## 验证链路

```text
build_demo_data()
↓
写入 SQLite klines
↓
MarketDataRepository.get_data_feed()
↓
BacktestEngine.run()
↓
TradingRepository.save_backtest_result()
↓
strategy_runs / orders / trades / equity_curve
↓
查询并打印结果
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_database_backtest.py
```

## 前置条件

不需要 Binance。

不需要 MySQL。

不需要 API Key。

## 使用的数据库

```text
sqlite:///:memory:
```

也就是说，数据库只存在于本次进程内，脚本结束后数据会消失。

## 输出内容

脚本会打印：

```text
saved run_id
recent runs
orders
trades
equity points
final equity
```

## 涉及表

```text
klines
strategy_runs
orders
trades
equity_curve
```

## 适合用来验证什么

```text
1. ORM 表能否创建
2. MarketDataRepository 能否读出 DataFeed
3. TradingRepository 能否保存回测结果
4. 回测结果相关表是否能查询
```

## 注意事项

这个脚本是 SQLite 内存演示，不等同于真实 MySQL 验证。真实 MySQL 闭环请看 `run_market_data_pipeline.py`。
