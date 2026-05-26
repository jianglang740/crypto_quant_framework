# basic_strategy.py 说明文档

## 作用

`basic_strategy.py` 提供一个可复用的演示策略和一组内置假行情数据，主要用于快速验证回测引擎、绩效分析和数据库保存流程。

它不是独立交易脚本的最终形态，更像是其他示例的公共依赖。

## 主要内容

### `MomentumMovingAverageFuturesStrategy`

这是一个合约模式的动量均线策略：

```text
短均线上穿长均线 + N 周期涨幅超过阈值 -> 开多
短均线下穿长均线 -> 平多并开空
停止时 -> 平掉多头和空头
```

默认参数：

```text
short_window = 7
long_window = 14
return_window = 7
return_threshold = 0.005
position_ratio = 0.95
trading_mode = FUTURE
```

### `build_demo_data()`

构造一组内置的 ETH/USDT 15m 假 K 线，用于离线回测。

特点：

```text
不连接交易所
不连接数据库
不需要 API Key
不需要 MySQL
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/basic_strategy.py
```

## 输出内容

脚本会打印：

```text
最终账户状态
绩效分析结果
订单数量
成交数量
```

## 涉及模块

```text
BacktestEngine
BacktestConfig
DataFeed
BarData
PerformanceAnalyzer
StrategyBase
```

## 是否访问外部资源

不会访问外部资源。

## 是否写数据库

不会写数据库。

## 适合用来验证什么

```text
1. 策略类如何继承 StrategyBase
2. on_bar() 中如何写交易逻辑
3. 回测引擎如何撮合订单
4. 合约模式下多空仓位如何变化
5. PerformanceAnalyzer 如何分析回测结果
```

## 注意事项

这个策略只用于框架功能演示，不代表可实盘交易的成熟策略。内置行情是手工构造的假数据，不能作为策略有效性的依据。
