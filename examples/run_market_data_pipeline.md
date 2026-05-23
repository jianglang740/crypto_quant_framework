# run_market_data_pipeline.py 说明文档

## 作用

`run_market_data_pipeline.py` 是真实行情数据库闭环验证脚本。

它会从 Binance 拉取真实 BTC/USDT 1m K 线，通过 `MarketDataPipeline` 清洗校验并写入 MySQL，再从 MySQL 读回 `DataFeed` 运行回测，最后把回测结果保存回 MySQL。

## 验证链路

```text
Binance 真实行情
↓
SOCKS5 代理
↓
BinanceClient
↓
MarketDataFetcher
↓
MarketDataPipeline.fetch_clean_store()
↓
clean_and_validate_bars()
↓
MarketDataRepository.upsert_klines()
↓
MySQL klines
↓
MarketDataRepository.get_data_feed()
↓
DataFeed
↓
SimpleMovingAverageStrategy
↓
BacktestEngine.run()
↓
TradingRepository.save_backtest_result()
↓
MySQL strategy_runs / orders / trades / equity_curve
```

## 默认配置

```text
SYMBOL = BTC/USDT
TIMEFRAME = 1m
START = 2024-06-01 08:00
END = 2024-06-01 10:00
```

MySQL：

```text
host = 127.0.0.1
port = 3306
username = crypto_quant_user
database = crypto_quant
```

Binance：

```text
sandbox = False
trading_mode = SPOT
proxy = socks5h://127.0.0.1:1080
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_market_data_pipeline.py
```

运行时会提示输入本地 MySQL 密码。

## 前置条件

需要：

```text
1. 本地 MySQL 正常运行
2. crypto_quant 数据库存在
3. crypto_quant_user 有权限访问该数据库
4. 本地 SOCKS5 代理 127.0.0.1:1080 可用
5. 能访问 Binance 行情接口
```

不需要 Binance API Key，因为这里拉的是公开行情。

## 输出内容

脚本会打印：

```text
完整数据库闭环验证完成
symbol
timeframe
Binance 拉取 K线数量
清洗后入库 K线数量
从 MySQL 读回 DataFeed 数量
缺失区间数量
回测订单数量
回测成交数量
权益曲线点数
回测结果 run_id
回测结果状态
最终权益
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
1. Binance 真实行情是否能拉取
2. MarketDataPipeline 是否能完成拉取、清洗、入库、读回
3. MySQL klines 是否能作为回测数据源
4. 真实行情回测结果是否能保存回 MySQL
```

## 注意事项

这是当前项目中最重要的行情数据库闭环示例之一。

如果在云服务器运行，通常不需要本地 SOCKS5 代理，可以删除或不传 `proxies` 配置。
