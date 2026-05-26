# simple_moving_average_strategy.py 说明文档

## 作用

`simple_moving_average_strategy.py` 定义一个最基础的简单移动平均线策略，用于演示框架中策略类的最小写法。

这个文件通常被其他示例导入，例如：

```text
run_backtest.py
run_live.py
run_market_data_pipeline.py
```

## 策略逻辑

策略类：

```python
SimpleMovingAverageStrategy
```

核心逻辑：

```text
收盘价进入队列
↓
等待累计到 slow_window 根 K 线
↓
计算 fast_ma 和 slow_ma
↓
fast_ma > slow_ma 且当前空仓 -> 买入
fast_ma < slow_ma 且当前有仓 -> 平仓
```

默认参数：

```text
fast_window = 5
slow_window = 20
trading_mode = SPOT
```

## 运行方式

这个文件本身只定义策略类，没有 `main()`，通常不单独运行。

如果要看它如何使用，可以运行：

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_backtest.py
```

## 涉及模块

```text
StrategyBase
BarData
PositionSide
TradingMode
```

## 是否访问外部资源

不会访问外部资源。

## 是否写数据库

不会写数据库。

## 适合用来学习什么

```text
1. 如何继承 StrategyBase
2. 如何在 __init__ 中定义策略参数
3. 如何在 on_bar() 中读取 K 线
4. 如何通过 self.buy() 下单
5. 如何通过 self.close_position() 平仓
6. 如何通过 self.get_position() 判断当前持仓
```

## 注意事项

这个策略非常简单，只用于演示框架结构，不适合作为真实交易策略直接使用。
