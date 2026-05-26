# run_csv_backtest.py 说明文档

## 作用

`run_csv_backtest.py` 演示如何从本地 CSV 文件读取 K 线数据，并用这些数据运行回测。

它比 `run_backtest.py` 更接近真实回测，因为行情数据来自文件，而不是脚本中手工构造。

## 验证链路

```text
CSV 文件
↓
load_bars_from_csv()
↓
DataFeed
↓
MomentumMovingAverageFuturesStrategy
↓
BacktestEngine.run()
↓
PerformanceAnalyzer
↓
终端打印结果
```

## 默认配置

```text
CSV_PATH = data/ETH_USDT_USDT_15m.csv
SYMBOL = ETH/USDT
TIMEFRAME = 15m
```

策略参数：

```text
short_window = 7
long_window = 14
return_window = 7
return_threshold = 0.005
trading_mode = FUTURE
```

回测参数：

```text
initial_cash = 1000
commission_rate = 0.001
slippage_rate = 0
leverage = 50
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_csv_backtest.py
```

## 前置条件

需要本地存在：

```text
data/ETH_USDT_USDT_15m.csv
```

## 输出内容

脚本会打印：

```text
最终账户状态
绩效分析结果
订单数量
成交数量
```

## 是否访问外部资源

不会访问外部网络，只读取本地 CSV 文件。

## 是否写数据库

不会写数据库。

## 适合用来验证什么

```text
1. CSV 行情加载是否正常
2. DataFeed 是否能由 CSV 构造
3. 合约回测是否能运行
4. 绩效分析是否能处理回测结果
```

## 注意事项

CSV 文件路径是相对路径，运行脚本时建议在项目根目录执行，否则可能找不到文件。
