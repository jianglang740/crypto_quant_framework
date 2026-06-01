# 滚动累计收益率反转策略说明

对应脚本：`run_cusum_reversion_strategy.py`

## 1. 策略定位

这是一个 rolling 窗口反转策略，准确名称应理解为：

```text
Rolling Return Reversion
滚动累计收益率反转策略
```

它不是严格意义上的经典 CUSUM，而是统计最近 `nk` 根 K 线的累计 log return。

核心思想：

```text
最近 nk 根涨太多 -> 认为短期过热 -> 做空
最近 nk 根跌太多 -> 认为短期超跌 -> 做多
```

它更适合震荡或均值回归行情，不适合强趋势行情裸跑。

## 2. 当前默认参数

类默认参数：

```python
nk = 10
threshold = Decimal("0.03")
take_profit_rate = Decimal("0.018")
stop_loss_rate = Decimal("0.033")
position_ratio = Decimal("0.30")
volatility_window = 48
take_profit_vol_multiplier = Decimal("2.0")
stop_loss_vol_multiplier = Decimal("3.0")
```

`main()` 中实际使用：

```python
nk = 14
threshold = Decimal("0.07")
take_profit_rate = Decimal("0.018")
stop_loss_rate = Decimal("0.033")
position_ratio = Decimal("0.30")
volatility_window = 48
take_profit_vol_multiplier = Decimal("2.0")
stop_loss_vol_multiplier = Decimal("3.0")
```

| 参数 | 含义 |
|---|---|
| `nk` | rolling 窗口长度 |
| `threshold` | 最近 `nk` 根累计收益触发阈值 |
| `take_profit_rate` | 基础止盈比例 |
| `stop_loss_rate` | 基础止损比例 |
| `position_ratio` | 合约仓位比例 |
| `volatility_window` | 近期波动率计算窗口 |
| `take_profit_vol_multiplier` | 止盈波动率倍数 |
| `stop_loss_vol_multiplier` | 止损波动率倍数 |

## 3. 信号计算

策略在 `on_init()` 中一次性预计算信号：

```python
df["log_return"] = np.log(df["close"] / df["close"].shift(1)).fillna(0)
df["rolling_log_return"] = df["log_return"].rolling(window=self.nk).sum().fillna(0)
df["volatility"] = df["log_return"].rolling(window=self.volatility_window).std().fillna(0)
```

`rolling_log_return` 表示最近 `nk` 根 K 线的累计 log return。

`volatility` 表示最近 `volatility_window` 根 K 线的 log return 标准差，用来估算近期市场波动水平。

## 4. 当前交易方向

当前方向：

```python
rolling_log_return >= threshold -> signal = -1 -> 做空
rolling_log_return <= -threshold -> signal = 1  -> 做多
```

也就是：

```text
涨多了做空；
跌多了做多。
```

## 5. 做多逻辑

当信号为 `1`：

```python
_reverse_to_long(bar)
```

执行逻辑：

1. 如果当前有空头，先平空；
2. 如果当前没有多头，再开多。

## 6. 做空逻辑

当信号为 `-1`：

```python
_reverse_to_short(bar)
```

执行逻辑：

1. 如果当前有多头，先平多；
2. 如果当前没有空头，再开空。

## 7. 动态止盈止损

当前版本不再只使用固定止盈止损，而是在基础止盈止损率上结合近期波动率动态调整：

```python
dynamic_take_profit_rate = max(take_profit_rate, volatility * take_profit_vol_multiplier)
dynamic_stop_loss_rate = max(stop_loss_rate, volatility * stop_loss_vol_multiplier)
```

含义是：

```text
市场波动较小时，使用基础止盈止损率；
市场波动较大时，止盈止损会随近期波动率自动放宽。
```

多头收益率：

```python
pnl_rate = bar.close / long_position.entry_price - Decimal("1")
```

空头收益率：

```python
pnl_rate = short_position.entry_price / bar.close - Decimal("1")
```

如果：

```python
pnl_rate >= dynamic_take_profit_rate
```

则止盈。

如果：

```python
pnl_rate <= -dynamic_stop_loss_rate
```

则止损。

## 8. 仓位逻辑

仓位计算使用框架版合约逻辑：

```python
amount = self.account.available * leverage * self.position_ratio / price
```

注意当前 `position_ratio=0.30` 较激进，在 10 倍杠杆下名义敞口约为账户可用资金的 3 倍。

## 9. 当前回测表现

用上传的 ETH 15m 一年数据验证修正后的反转方向：

```text
final_equity: 11652.37
total_return: +16.52%
max_drawdown: -29.25%
trades: 42
profit_factor: 1.24
```

特点：

- 单策略盈利；
- 回撤仍然较大；
- 策略在趋势行情中仍可能逆势开仓；
- 当前版本已加入波动率动态止盈止损，历史表现需要重新回测确认；
- 不建议裸跑作为主策略。


