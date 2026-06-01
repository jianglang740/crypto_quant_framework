from decimal import Decimal

import numpy as np
from crypto_quant.analysis.bokeh_report import BokehBacktestReport #导入回测绩效绘图模块
from crypto_quant.analysis import PerformanceAnalyzer #导入绩效报告模块
from crypto_quant.config import BacktestConfig
from crypto_quant.data import BarData, load_bars_from_csv
from crypto_quant.engine import BacktestEngine
from crypto_quant.enums import PositionSide, TradingMode #导入持仓枚举和交易模式
from crypto_quant.strategy import StrategyBase #导入策略基类


CSV_PATH = "/Users/clinking/Documents/GitHub/crypto_quant_framework/ETH_USDT_5m_1year.csv"
SYMBOL = "ETH/USDT"
TIMEFRAME = "5m"


class RollingReturnReversionFuturesStrategy(StrategyBase):
    name = "rolling_return_reversion_futures"

    def __init__(
        self,
        nk: int = 10, #窗口长度
        threshold: Decimal = Decimal("0.03"), #阈值
        take_profit_rate: Decimal = Decimal("0.018"), #基础止盈率
        stop_loss_rate: Decimal = Decimal("0.033"), #基础止损率
        position_ratio: Decimal = Decimal("0.30"), #使用的资金比例
        volatility_window: int = 48, #波动率窗口长度
        take_profit_vol_multiplier: Decimal = Decimal("2.0"), #止盈波动率倍数
        stop_loss_vol_multiplier: Decimal = Decimal("3.0"), #止损波动率倍数
    ):
        super().__init__(trading_mode=TradingMode.FUTURE)  #super().__init__调用父类的构造方法（init），让子类实例拥有父类定义的属性和初始化逻辑
        self.nk = nk
        self.threshold = threshold
        self.take_profit_rate = take_profit_rate
        self.stop_loss_rate = stop_loss_rate
        self.position_ratio = position_ratio
        self.volatility_window = volatility_window
        self.take_profit_vol_multiplier = take_profit_vol_multiplier
        self.stop_loss_vol_multiplier = stop_loss_vol_multiplier
        self.signals: list[int] = [] #交易信号列表
        self.dynamic_take_profit_rates: list[Decimal] = [] #每根K线对应的动态止盈率
        self.dynamic_stop_loss_rates: list[Decimal] = [] #每根K线对应的动态止损率

    def on_init(self) -> None: #初始化方法，返回空值 
        if self.data is None:
            return
        df = self.data.to_dataframe() #转换成dataframe
        df["close"] = df["close"].astype(float) #转换成浮点数类型
        df["log_return"] = np.log(df["close"] / df["close"].shift(1)).fillna(0) #计算简单对数收益
        df["rolling_log_return"] = df["log_return"].rolling(window=self.nk).sum().fillna(0) #计算近n根k线的窗口内的收益率总和
        df["volatility"] = df["log_return"].rolling(window=self.volatility_window).std().fillna(0) #用更长窗口估算近期波动率
        threshold = float(self.threshold)
        df["reversion_signal"] = 0 #无交易信号，先把所有k线都设置成0，也就是默认一开始不操作，无信号
        #df.loc [条件，列名] = 值，即给满足条件的那一行赋值
        df.loc[df["rolling_log_return"] >= threshold, "reversion_signal"] = -1 #赋值-1，做空
        df.loc[df["rolling_log_return"] <= -threshold, "reversion_signal"] = 1 #赋值1，做多
        self.signals = [int(value) for value in df["reversion_signal"].tolist()] #转换成列表
        self.dynamic_take_profit_rates = [
            max(self.take_profit_rate, Decimal(str(value)) * self.take_profit_vol_multiplier)
            for value in df["volatility"].tolist()
        ]
        self.dynamic_stop_loss_rates = [
            max(self.stop_loss_rate, Decimal(str(value)) * self.stop_loss_vol_multiplier)
            for value in df["volatility"].tolist()
        ]

    def on_bar(self, bar: BarData) -> None:
        if self.data is None:
            return
        signal = self.signals[self.data.cursor] if self.data.cursor < len(self.signals) else 0 

        if self._check_take_profit_stop_loss(bar):
            return

        if signal == 1:
            self._reverse_to_long(bar)
        elif signal == -1:
            self._reverse_to_short(bar)

    def on_stop(self) -> None:
        if self.data is None or len(self.data) == 0:
            return
        symbol = self.data.current.symbol
        self.close_position(symbol, PositionSide.BOTH)
        self.close_position(symbol, PositionSide.SHORT)

    def _check_take_profit_stop_loss(self, bar: BarData) -> bool:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        take_profit_rate = self._current_take_profit_rate()
        stop_loss_rate = self._current_stop_loss_rate()
        if not long_position.is_flat and long_position.entry_price > 0:
            pnl_rate = bar.close / long_position.entry_price - Decimal("1")
            if pnl_rate >= take_profit_rate or pnl_rate <= -stop_loss_rate:
                self.close_position(bar.symbol, PositionSide.BOTH)
                return True
        if not short_position.is_flat and short_position.entry_price > 0:
            pnl_rate = short_position.entry_price / bar.close - Decimal("1")
            if pnl_rate >= take_profit_rate or pnl_rate <= -stop_loss_rate:
                self.cover(bar.symbol, abs(short_position.amount))
                return True
        return False

    def _current_take_profit_rate(self) -> Decimal:
        if self.data is None or self.data.cursor >= len(self.dynamic_take_profit_rates):
            return self.take_profit_rate
        return self.dynamic_take_profit_rates[self.data.cursor]

    def _current_stop_loss_rate(self) -> Decimal:
        if self.data is None or self.data.cursor >= len(self.dynamic_stop_loss_rates):
            return self.stop_loss_rate
        return self.dynamic_stop_loss_rates[self.data.cursor]

    def _reverse_to_long(self, bar: BarData) -> None:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not short_position.is_flat:
            self.cover(bar.symbol, abs(short_position.amount))
        if long_position.is_flat:
            self.buy(bar.symbol, self._order_amount(bar.close))

    def _reverse_to_short(self, bar: BarData) -> None:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not long_position.is_flat:
            self.close_position(bar.symbol, PositionSide.BOTH)
        if short_position.is_flat:
            self.short(bar.symbol, self._order_amount(bar.close))

    def _order_amount(self, price: Decimal) -> Decimal:
        leverage = self.engine.config.leverage if self.engine is not None else Decimal("1")
        amount = self.account.available * leverage * self.position_ratio / price
        return max(amount, Decimal("0"))


def main() -> None:
    data = load_bars_from_csv(
        path=CSV_PATH,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
    )

    strategy = RollingReturnReversionFuturesStrategy(
        nk=14,
        threshold=Decimal("0.07"),
        take_profit_rate=Decimal("0.018"),
        stop_loss_rate=Decimal("0.033"),
        position_ratio=Decimal("0.30"),
        volatility_window=72,
        take_profit_vol_multiplier=Decimal("2.8"),
        stop_loss_vol_multiplier=Decimal("3"),
    )
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=Decimal("10000"),
            commission_rate=Decimal("0.001"),
            slippage_rate=Decimal("0"),
            leverage=Decimal("10"),
        )
    )
    result = engine.run(strategy, data)
    report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)
    BokehBacktestReport(
        result,
        data,
        title="Rolling Return Reversion Strategy Report",
    ).save("rolling_return_reversion_strategy_report.html")

    print("========== 滚动累计收益率反转策略 CSV 回测 ==========")
    print(result.final_account)
    print(report)
    print(f"orders: {len(result.orders)}")
    print(f"trades: {len(result.trades)}")


if __name__ == "__main__":
    main()