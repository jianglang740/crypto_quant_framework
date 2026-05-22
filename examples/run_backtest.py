from datetime import datetime, timezone
from decimal import Decimal #高精度计算

from crypto_quant.analysis import PerformanceAnalyzer #导入绩效分析模块
from crypto_quant.config import BacktestConfig #导入回测模块的相关配置文件
from crypto_quant.data import BarData, DataFeed #导入核心的“单根k线”和“数据线”以及“数据线源”模块
from crypto_quant.engine import BacktestEngine #导入回测引擎模块
from crypto_quant.enums import TradingMode #导入枚举模块里的交易类型模块
from examples.simple_moving_average_strategy import SimpleMovingAverageStrategy #导入已经写好的简单移动平均线策略类

'''
每一分钟生成一根 K 线；
每根 K 线价格比上一根略微高一点；
构造出一个非常简单的上涨行情

这里不是因为 DataFeed 的设计要求每个字段都设置索引，
而是这个示例为了快速构造 60 根“假 K 线”，用 index 让每根 K 线的时间和价格都稍微变化一下

这段代码本质上是一个 Python 列表推导式：
bars = [
    BarData(...)
    for index in range(60)
]
也就是说，index 会从 0 到 59 变化，所以会生成 60 根 K 线
'''

bars = [ #构造“虚假的”用于回测实例的单根k线列表
    BarData(
        symbol="BTC/USDT",
        timeframe="1m", #k线的时间周期
        datetime=datetime(2026, 1, 1, 0, index, tzinfo=timezone.utc),
        open=Decimal("100000") + Decimal(index),
        high=Decimal("100800") + Decimal(index),
        low=Decimal("99990") + Decimal(index),
        close=Decimal("101000") + Decimal(index),
        volume=Decimal("10"),
    )
    for index in range(60)
]

strategy = SimpleMovingAverageStrategy(trading_mode=TradingMode.SPOT) #绑定策略为简单移动平均线策略和交易类型为现货交易
engine = BacktestEngine(BacktestConfig(initial_cash=Decimal("10000"))) #绑定回测引擎并设置初始资金
result = engine.run(strategy, DataFeed(bars)) #逐根k线的运行策略回测
report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades) #打印交易绩效报告

print(result.final_account) #输出账户最后情况
print(report) #输出交易绩效报告

'''
result = engine.run(strategy, DataFeed(bars)):

把策略 strategy 和行情数据 DataFeed(bars) 交给回测引擎 engine；
回测引擎开始按时间顺序一根一根读取 K 线；
每读到一根 K 线，就把这根 K 线交给策略判断；
策略如果产生买卖指令，引擎就模拟成交、更新账户；
全部 K 线跑完后，返回完整回测结果 result。后续可以通过result来调取回测结果
'''