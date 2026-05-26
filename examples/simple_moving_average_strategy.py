from collections import deque #从 Python 内置的 collections 模块中导入 deque 双端队列数据结构
from decimal import Decimal

from crypto_quant.data.feed import BarData #导入单根k线模块
from crypto_quant.enums import PositionSide, TradingMode #从枚举模块里导入持仓方向和交易类型模块
from crypto_quant.strategy.base import StrategyBase #导入策略基类模块

# super().__init__的作用是在子类的构造方法里，调用父类的构造方法，让父类完成它的初始化工作，
# 即__init__：类的构造方法，创建对象时自动执行，用来初始化属性，而super()：代表父类，专门用来调用父类的方法

class SimpleMovingAverageStrategy(StrategyBase): #定义简单移动平均线策略类并继承策略基类
    name = "simple_moving_average" #自定义名字，策略名称，用于回测结果、订单、成交记录中标识该策略

    def __init__(self, fast_window: int = 5, slow_window: int = 20, trading_mode: TradingMode = TradingMode.SPOT): #初始化策略参数，并指定交易模式，默认是现货交易
        super().__init__(trading_mode=trading_mode)  #调用父类的构造方法，让父类完成它的初始化工作
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.closes: deque[Decimal] = deque(maxlen=slow_window) #类型标注写法，表示以慢线为基准创建一个最大容量的deque类型队列，超过长度后会自动丢弃旧数据，例如创建一个最多保存最近 20 个收盘价的队列

    def on_bar(self, bar: BarData) -> None: #-> None 是 Python 的类型标注，表示这个函数的返回值类型；bar: BarData表示参数 bar 预期是一个 BarData 类型
        self.closes.append(bar.close) #向deque队列中增加收盘价数据，每来一根 K 线，就把收盘价存进去
        if len(self.closes) < self.slow_window: #如果收盘价数据量小于慢线窗口长度就不执行，还不够计算慢均线需要的数量，就先不交易直接返回
            return
        fast_ma = sum(list(self.closes)[-self.fast_window:]) / Decimal(self.fast_window) #快线，假设self.fast_window = 5，那么list(self.closes)[-self.fast_window:]等价于list(self.closes)[-5:]，即取最后 5 个收盘价
        slow_ma = sum(self.closes) / Decimal(self.slow_window) #计算最近 slow_window 根 K 线的收盘价平均值，也就是慢均线。
        position = self.get_position(bar.symbol, PositionSide.BOTH) #获取账户在当前交易对上的持仓信息
        if fast_ma > slow_ma and position.is_flat: #如果快线大于慢线，且当前针对该交易对没有持仓就买入
            self.buy(bar.symbol, Decimal("0.01")) 
        elif fast_ma < slow_ma and not position.is_flat: #如果快线小于慢线，且当前针对该交易对不是空仓，也就是当前有持仓，就平仓
            self.close_position(bar.symbol)

'''
注：

这里我只是为了简单演示一下怎么利用这个框架写策略而已
所以这个均线策略很简单，不能拿去交易
'''