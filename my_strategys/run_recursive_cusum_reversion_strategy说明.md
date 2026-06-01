# 递归 CUSUM 复刻策略说明

对应脚本：`run_recursive_cusum_reversion_strategy.py`

## 1. 策略定位

这是原始的 CUSUM 逻辑的策略。

它和 `run_cusum_reversion_strategy.py` 的 rolling 窗口版本不同。

当前策略采用：

```text
递归累计 CUSUM + 突破阈值后清零
```

核心用途：

1. 对齐和验证 `swap.py` 的原始逻辑；
2. 和框架版回测结果做对照；
3. 观察原始策略在框架账户模型下的表现。

## 2. 当前默认参数

```python
threshold = Decimal("0.07")
take_profit_rate = Decimal("0.018")
stop_loss_rate = Decimal("0.033")
position_ratio = Decimal("0.30")
```

注意：这个版本没有 `nk` 参数。

原因是 `swap.py` 里的原始 CUSUM 逻辑虽然传了 `NK`，但实际计算中没有使用 `NK`。为了避免误解，这个复刻版已经去掉 `nk`。

## 3. 信号计算

每根 K 线计算：

```python
log_return = log(close[i] / close[i - 1])
```

然后维护两个累计值：

```python
pos_sum
neg_sum
```

更新规则：

```python
pos_sum = max(0.0, pos_sum + log_return)
neg_sum = min(0.0, neg_sum + log_return)
```

含义：

| 变量 | 含义 |
|---|---|
| `pos_sum` | 正向累计变化 |
| `neg_sum` | 负向累计变化 |

## 4. 突破阈值后清零

如果：

```python
pos_sum >= threshold
```

则生成信号：

```python
signal = 1
```

然后：

```python
pos_sum = 0
neg_sum = 0
```

如果：

```python
neg_sum <= -threshold
```

则生成信号：

```python
signal = -1
```

然后同样清零。

这就是“递归 CUSUM 且突破阈值后清零”。

它不是固定看最近 N 根 K 线，而是从上次清零后开始累计，直到累计变化达到阈值。

## 5. 当前交易方向

当前方向和 `swap.py` 保持一致：

```text
signal = 1  -> 做多
signal = -1 -> 做空
```

如果已有反向仓位，则先平反向仓位，再开新方向仓位。

## 6. 止盈止损

止盈：

```python
take_profit_rate = 0.018
```

止损：

```python
stop_loss_rate = 0.033
```

多头收益率：

```python
bar.close / entry_price - 1
```

空头收益率：

```python
entry_price / bar.close - 1
```

## 7. 仓位逻辑

仓位计算使用框架版合约逻辑：

```python
amount = self.account.available * leverage * self.position_ratio / price
```

当前 `position_ratio=0.30`，如果杠杆为 10 倍，则名义仓位约为账户可用资金的 3 倍。

这是比较激进的设置。

## 8. 当前回测表现

使用上传的 ETH 15m 一年数据，当前结果：

```text
final_equity: 46996.38
total_return: +369.96%
max_drawdown: -54.57%
trade_count: 304
win_rate: 71.71%
profit_factor: 1.19
```

特点：

- 收益很高；
- 回撤非常大；
- 交易频率高；
- 杠杆风险大；
- 不适合作为当前主策略直接使用。

## 9. 和 rolling 版本的区别

| 对比项 | 递归 CUSUM | rolling 反转 |
|---|---|---|
| 是否使用固定窗口 | 否 | 是 |
| 是否使用 `nk` | 否 | 是 |
| 触发后是否清零 | 是 | 否 |
| 关注对象 | 从上次清零后的累计偏移 | 最近 `nk` 根累计收益 |



