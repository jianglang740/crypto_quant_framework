# run_backtest.py 说明文档

## 作用

`run_backtest.py` 是最基础的回测入门示例。

它用程序手动构造 60 根假的 BTC/USDT 1m K 线，然后运行 `SimpleMovingAverageStrategy`，最后打印账户结果和绩效报告。

## 验证链路

```text
手工构造 BarData
↓
组成 DataFeed
↓
SimpleMovingAverageStrategy
↓
BacktestEngine.run()
↓
BacktestResult
↓
PerformanceAnalyzer
↓
终端打印结果
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_backtest.py
```

## 前置条件

不需要 Binance。

不需要 MySQL。

不需要 API Key。

## 输出内容

脚本会打印：

```text
最终账户状态
绩效分析报告
```

## 涉及模块

```text
BarData
DataFeed
BacktestEngine
BacktestConfig
PerformanceAnalyzer
SimpleMovingAverageStrategy
TradingMode
```

## 是否访问外部资源

不会访问外部资源。

## 是否写数据库

不会写数据库。

## 适合用来验证什么

```text
1. 回测引擎能否运行
2. 策略能否收到 K 线
3. 策略能否产生买入和平仓信号
4. BacktestResult 是否能正常生成
5. PerformanceAnalyzer 是否能正常分析
```

## 注意事项

这里的 K 线是假数据，只用于快速验证框架，不代表真实行情。
