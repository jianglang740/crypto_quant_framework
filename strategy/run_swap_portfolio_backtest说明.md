# 趋势 + 趋势过滤反转组合策略说明

对应脚本：`run_swap_portfolio_backtest.py`

## 1. 策略定位

这是组合回测脚本，用于验证框架的组合引擎 `PortfolioBacktestEngine`，并测试两个策略如何协同：

```text
动量趋势策略
+
趋势过滤 rolling 反转策略
```

当前组合不是最终实盘版本，而是一个研究版本。

核心思想：

1. 动量趋势策略负责判断大方向；
2. rolling 反转策略负责捕捉短期过度偏离；
3. rolling 反转策略会参考趋势方向，避免强趋势中逆势开仓。

## 2. 当前包含的两个策略

脚本内部包含：

```python
MomentumTrendFuturesStrategy
TrendFilteredRollingReturnReversionFuturesStrategy
```

其中：

| 策略 | 作用 |
|---|---|
| `MomentumTrendFuturesStrategy` | 判断趋势方向并独立交易 |
| `TrendFilteredRollingReturnReversionFuturesStrategy` | 在趋势过滤后做 rolling 反转交易 |

## 3. 动量趋势策略参数

当前组合脚本里的趋势策略参数已经同步最新优化版：

```python
short_window = 10
long_window = 30
return_window = 4
return_threshold = Decimal("0.003")
min_ma_gap = Decimal("0.002")
stop_loss_rate = Decimal("0.015")
position_ratio = Decimal("0.05")
```

它的逻辑和 `run_momentum_trend_strategy.py` 中的单策略版本一致。

做多：

```text
金叉 + 正向动量 + 均线距离达标
```

做空：

```text
死叉 + 负向动量 + 均线距离达标
```

同时它维护：

```python
trend_state
```

取值：

```text
up
down
neutral
```

## 4. rolling 反转策略参数

当前组合脚本中的反转策略参数：

```python
nk = 14
threshold = Decimal("0.07")
take_profit_rate = Decimal("0.018")
stop_loss_rate = Decimal("0.033")
position_ratio = Decimal("0.10")
```

相比单策略 rolling 反转版本，这里把 `position_ratio` 降低到了 `0.10`，避免组合风险过高。

## 5. rolling 原始反转信号

先计算最近 `nk` 根累计收益：

```python
rolling_return = closes[-1] / closes[0] - Decimal("1")
```

原始信号：

```text
rolling_return >= threshold  -> 做空
rolling_return <= -threshold -> 做多
```

也就是：

```text
涨多了做空；
跌多了做多。
```

## 6. 趋势过滤逻辑

组合脚本的核心改进在这里。

rolling 反转策略会读取趋势策略的：

```python
self.trend_strategy.trend_state
```

过滤规则：

```text
如果 trend_state == "up"：
    禁止 rolling 做空
    只允许跌多后做多

如果 trend_state == "down"：
    禁止 rolling 做多
    只允许涨多后做空

如果 trend_state == "neutral"：
    rolling 可以双向反转
```

对应代码逻辑：

```python
if self.trend_strategy.trend_state == "up" and signal == -1:
    return 0
if self.trend_strategy.trend_state == "down" and signal == 1:
    return 0
return signal
```

## 7. 为什么这样组合

rolling 反转策略裸跑的问题是：

```text
趋势行情中容易不断逆势止损。
```

例如强上涨行情：

```text
最近 nk 根涨幅过大 -> rolling 原始逻辑想做空
但趋势仍然向上 -> 空单容易止损
```

所以组合策略让动量趋势策略充当环境过滤器：

```text
上涨趋势中，不做逆势空单；
下跌趋势中，不做逆势多单；
无明显趋势时，允许震荡反转。
```

## 8. 当前回测结果

使用上传的 ETH 15m 一年数据验证：

```text
portfolio final: 9648.80
return: -3.51%
max_drawdown: -5.00%
trades: 32
profit_factor: 0.64
```

分策略交易数：

```text
momentum_trend_futures:
orders 25
trades 25

trend_filtered_rolling_return_reversion_futures:
orders 7
trades 7
```

## 9. 当前结果解读

这个组合版本有几个特点：

1. 最大回撤很低，约 5%；
2. 组合收益暂时不好；
3. rolling 反转策略交易很少；
4. rolling 反转部分目前拖累组合；
5. 当前更像风险控制验证版，而不是收益最优版。

## 10. 后续优化方向

下一步建议重点分析 rolling 反转那 7 笔交易：

1. 是止损导致亏损，还是止盈太近；
2. 是趋势过滤过严，还是过滤方向仍然不够；
3. 是否应该只在 `neutral` 状态启用 rolling；
4. 是否应该调低 `position_ratio`；
5. 是否应该调高 `threshold`，只做更极端偏离；
6. 是否加入止损后冷却期。

可能的下一版组合逻辑：

```text
趋势策略独立运行；
rolling 反转只在 trend_state == neutral 时启用；
或者 rolling 只作为趋势回调加仓信号，不独立反手。
```

## 11. 当前用途

当前脚本适合用于：

1. 验证 `PortfolioBacktestEngine`；
2. 研究多策略共享账户时的行为；
3. 测试趋势过滤对反转策略的影响；
4. 后续组合策略优化的基础版本。
