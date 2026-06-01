# 动量 + 趋势策略说明

对应脚本：`run_momentum_trend_strategy.py`

## 1. 策略定位

这是当前 `my_strategy` 文件夹里重点优化过的单策略版本，定位是低频趋势跟随策略。

它不是高频震荡策略，而是尽量只在趋势刚刚形成、动量方向一致、短长均线已经拉开一定距离时进场。

核心思想：

```text
短均线有效上穿长均线 + 近期上涨动量确认 -> 做多
短均线有效下穿长均线 + 近期下跌动量确认 -> 做空
```

策略同时带有基础止损，避免单笔亏损无限扩大。

## 2. 当前默认参数

```python
short_window = 10
long_window = 30
return_window = 4
return_threshold = Decimal("0.003")
min_ma_gap = Decimal("0.002")
stop_loss_rate = Decimal("0.015")
position_ratio = Decimal("0.05")
```

按照当前上传数据的实际周期 `15m` 理解：

| 参数 | 含义 |
|---|---|
| `short_window=10` | 最近 10 根 K 线短均线，约 2.5 小时 |
| `long_window=30` | 最近 30 根 K 线长均线，约 7.5 小时 |
| `return_window=4` | 最近 4 根 K 线收益率，约 1 小时动量 |
| `return_threshold=0.003` | 最近 1 小时涨跌幅至少达到 0.3% |
| `min_ma_gap=0.002` | 短长均线差距至少达到 0.2% |
| `stop_loss_rate=0.015` | 单笔亏损 1.5% 止损 |
| `position_ratio=0.05` | 使用 5% 保证金比例开仓 |

在 10 倍杠杆下，名义仓位约等于：

```text
账户可用资金 * 10 * 0.05 = 账户可用资金 * 0.5
```

也就是每次开仓约 0.5 倍账户权益名义敞口。

## 3. 指标计算

每根 K 线到来后，策略会维护一个 close 缓存，然后计算：

```python
short_ma_previous
long_ma_previous
short_ma_current
long_ma_current
period_return
ma_gap
```

含义如下：

| 指标 | 含义 |
|---|---|
| `short_ma_previous` | 上一根 K 线时的短均线 |
| `long_ma_previous` | 上一根 K 线时的长均线 |
| `short_ma_current` | 当前短均线 |
| `long_ma_current` | 当前长均线 |
| `period_return` | 当前价格相对 `return_window` 根前的收益率 |
| `ma_gap` | 短长均线当前距离 |

`ma_gap` 的计算方式：

```python
ma_gap = abs(short_ma_current / long_ma_current - Decimal("1"))
```

## 4. 趋势状态

策略内部维护：

```python
self.trend_state
```

可能取值：

```text
up
down
neutral
```

判断逻辑：

```text
如果短长均线距离不足 min_ma_gap -> neutral
如果短均线在长均线上方 -> up
如果短均线在长均线下方 -> down
```

这个状态在单策略里主要用于记录趋势环境，在组合策略中可以被 rolling 反转策略用于趋势过滤。

## 5. 做多逻辑

做多必须同时满足：

```python
golden_cross
and period_return >= return_threshold
and ma_gap >= min_ma_gap
```

其中：

```python
golden_cross = short_ma_previous <= long_ma_previous and short_ma_current > long_ma_current
```

含义是：

```text
短均线刚刚从下方上穿长均线。
```

如果触发做多信号：

1. 如果当前有空头，先平空；
2. 如果当前没有多头，再开多。

## 6. 做空逻辑

做空必须同时满足：

```python
death_cross
and period_return <= -return_threshold
and ma_gap >= min_ma_gap
```

其中：

```python
death_cross = short_ma_previous >= long_ma_previous and short_ma_current < long_ma_current
```

含义是：

```text
短均线刚刚从上方下穿长均线。
```

如果触发做空信号：

1. 如果当前有多头，先平多；
2. 如果当前没有空头，再开空。

## 7. 止损逻辑

多头止损：

```python
bar.close / long_position.entry_price - Decimal("1") <= -stop_loss_rate
```

空头止损：

```python
short_position.entry_price / bar.close - Decimal("1") <= -stop_loss_rate
```

当前默认止损为 1.5%。

## 8. 仓位逻辑

仓位计算使用框架版合约逻辑：

```python
amount = self.account.available * leverage * self.position_ratio / price
```

它表示：

```text
开仓数量 = 可用资金 * 杠杆 * 仓位比例 / 当前价格
```

## 9. 当前回测表现

使用上传的 ETH 15m 一年数据，当前结果：

```text
final_equity: 15007.99
total_return: +50.08%
max_drawdown: -15.24%
trade_count: 30
closed_trade_count: 15
win_rate: 13.33%
profit_factor: 3.53
```

特点：

- 交易次数很少；
- 胜率低；
- 单笔盈利较大；
- 更像趋势策略；
- 当前是主策略候选版本。


