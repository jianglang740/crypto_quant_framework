import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ====================== 1. 加载你的 ETH K线数据 ======================
# 这是你自己的文件路径，直接用
data = pd.read_csv("/Users/clinking/开发/quant/data/ETH_USDT_USDT_15m.csv")

# 修复时间列 + 设置索引
data["datetime"] = pd.to_datetime(data["datetime"])  # 修复语法
data.set_index("datetime", inplace=True)             # 真正把时间变成索引

# ====================== 2. CUSUM 策略函数（已修复） ======================
def cusum_filter(prices, c=0.07, use_log=True):
    """
    CUSUM 变点检测（趋势反转过滤器）
    :param prices: pd.Series 价格序列（索引为时间）
    :param c: 触发阈值，0.02 = 2%（ETH 15分钟K线用这个更合适）
    :param use_log: 是否用对数收益形式计算
    :return: buy_signals, sell_signals
    """
    prices = prices.copy()
    buy_signals = pd.Series(False, index=prices.index)
    sell_signals = pd.Series(False, index=prices.index)

    if use_log:
        log_prices = np.log(prices)
        high_so_far = log_prices.cummax()
        buy_cond = log_prices <= high_so_far - np.log(1 + c)
        
        low_so_far = log_prices.cummin()
        sell_cond = log_prices >= low_so_far + np.log(1 + c)
    else:
        high_so_far = prices.cummax()
        low_so_far = prices.cummin()
        buy_cond = (high_so_far - prices) / high_so_far >= c
        sell_cond = (prices - low_so_far) / low_so_far >= c

    buy_signals[buy_cond] = True
    sell_signals[sell_cond] = True

    return buy_signals, sell_signals

# ====================== 3. 运行策略 ======================
prices = data["close"]  # 直接用你的ETH收盘价
buy, sell = cusum_filter(prices, c=0.07, use_log=True)  # 2% 波动触发信号

# ====================== 4. 画图（K线 + 买卖点） ======================
plt.figure(figsize=(14, 7))
plt.plot(prices.index, prices.values, label="ETH/USDT 15min", color="#1f77b4", linewidth=1)

# 买入信号（绿色上三角）
plt.scatter(prices[buy].index, prices[buy].values,
            marker="^", color="lime", s=80, label="Buy Signal")

# 卖出信号（红色下三角）
plt.scatter(prices[sell].index, prices[sell].values,
            marker="v", color="red", s=80, label="Sell Signal")

plt.title("ETH 15min - CUSUM 趋势交易策略", fontsize=14)
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()