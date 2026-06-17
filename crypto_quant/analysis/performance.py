from dataclasses import dataclass
from decimal import Decimal
from math import sqrt

from crypto_quant.strategy.base import Trade

#先定义绩效指标类，罗列所需的指标字段名字和类型
@dataclass(frozen=True, slots=True)
class PerformanceReport:
    initial_equity: Decimal #初始权益
    final_equity: Decimal #最终权益
    total_return: Decimal #总收益率
    annual_return: Decimal #年化收益率
    volatility: float #年化波动率
    max_drawdown: Decimal #最大回撤
    sharpe_ratio: float #夏普比率
    sortino_ratio: float #索提诺比率
    calmar_ratio: float #卡尔玛比率
    trade_count: int #总交易次数
    closed_trade_count: int #已平仓的交易次数
    win_rate: Decimal #胜率
    profit_factor: Decimal #盈利因子 = 总盈利金额 / 总亏损金额，>1系统长期有利，>1.5优质
    gross_profit: Decimal #所有盈利单子合计盈利总额
    gross_loss: Decimal #所有亏损单子合计亏损总额（正数存储）
    average_win: Decimal #平均每笔盈利单盈利金额
    average_loss: Decimal #平均每笔亏损单亏损金额
    max_win: Decimal #历史单笔最大盈利
    max_loss: Decimal #历史单笔最大亏损


class PerformanceAnalyzer:
    def __init__(self, periods_per_year: int = 365):
        self.periods_per_year = periods_per_year #加密市场按一年365天计算，这里默认做的k线周期为日线，但实际生产过程中需要根据实际情况调整

    def analyze(self, equity_curve: list[tuple[object, Decimal]], trades: list[Trade]) -> PerformanceReport: #使用回测或实盘过程中产生的权益记录和成交记录来生成绩效报告
        if not equity_curve:
            return self._empty_report() #返回一个空的绩效报告，避免程序直接报错
        equities = [equity for _, equity in equity_curve] #遍历 equity_curve 里的每一个包裹，把每个包裹拆开： _ 接收时间戳， equity 接收权益值，这是一个约定俗成的占位符，意思是"我不需要这个值"（时间戳暂时不用）
        returns = self.returns(equity_curve)
        initial_equity = equities[0] #初始资金等于遍历结果列表的0索引位置对应的值
        final_equity = equities[-1] #最终权益等于遍历结果列表的-1索引位置对应的值
        total_return = final_equity / initial_equity - Decimal("1") if initial_equity else Decimal("0") #总收益率 = (最终权益 / 初始权益) - 1，如果初始资金不存在就返回0
        annual_return = self._annual_return(total_return, len(equities)) #调用 _annual_return 方法，计算"年化收益率"
        max_drawdown = self._max_drawdown(equities) #传入equities列表数据调用最大回撤函数计算最大回撤
        volatility = self._volatility(returns)
        sharpe_ratio = self._sharpe_ratio(returns)
        sortino_ratio = self._sortino_ratio(returns)
        calmar_ratio = float(annual_return / abs(max_drawdown)) if max_drawdown else 0.0
        realized_pnls = self.realized_pnls(trades) #计算已实现盈亏，计算每笔已闭合交易的盈亏
        gross_profit = sum((pnl for pnl in realized_pnls if pnl > 0), Decimal("0")) #总盈利 = 所有正数盈亏之和
        gross_loss = sum((pnl for pnl in realized_pnls if pnl <= 0), Decimal("0")) #总亏损 = 所有负数盈亏之和（正数存储）
        wins = [pnl for pnl in realized_pnls if pnl > 0] #盈利交易列表
        losses = [pnl for pnl in realized_pnls if pnl <= 0] #亏损交易列表
        closed_count = len(realized_pnls)#已闭合交易数量
        win_rate = Decimal(len(wins)) / Decimal(closed_count) if closed_count else Decimal("0") #胜率 = 盈利次数 / 总次数
        profit_factor = gross_profit / abs(gross_loss) if gross_loss else Decimal("0") #盈利因子 = 总盈利 / 总亏损
        average_win = gross_profit / Decimal(len(wins)) if wins else Decimal("0") #平均盈利
        average_loss = gross_loss / Decimal(len(losses)) if losses else Decimal("0") #平均亏损
        max_win = max(wins) if wins else Decimal("0") #最大单笔盈利
        max_loss = min(losses) if losses else Decimal("0") #最大单笔亏损
        return PerformanceReport(
            initial_equity=initial_equity,
            final_equity=final_equity,
            total_return=total_return,
            annual_return=annual_return,
            volatility=volatility,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            trade_count=len(trades),
            closed_trade_count=closed_count,
            win_rate=win_rate,
            profit_factor=profit_factor,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            average_win=average_win,
            average_loss=average_loss,
            max_win=max_win,
            max_loss=max_loss,
        ) #返回绩效报告

    def returns(self, equity_curve: list[tuple[object, Decimal]]) -> list[float]:
        equities = [equity for _, equity in equity_curve]
        return [float(equities[i] / equities[i - 1] - Decimal("1")) for i in range(1, len(equities)) if equities[i - 1]]

    def drawdowns(self, equity_curve: list[tuple[object, Decimal]]) -> list[tuple[object, Decimal]]:
        if not equity_curve:
            return []
        peak = equity_curve[0][1]
        result = []
        for timestamp, equity in equity_curve:
            peak = max(peak, equity)
            drawdown = equity / peak - Decimal("1") if peak else Decimal("0")
            result.append((timestamp, drawdown))
        return result

    def realized_pnls(self, trades: list[Trade]) -> list[Decimal]:
        amount = Decimal("0")
        entry_price = Decimal("0")
        entry_fee = Decimal("0")
        realized_pnls: list[Decimal] = []
        for trade in trades:
            signed_amount = trade.amount if trade.side.value == "buy" else -trade.amount
            if amount == 0 or (amount > 0) == (signed_amount > 0):
                total_amount = abs(amount) + abs(signed_amount)
                entry_price = (entry_price * abs(amount) + trade.price * abs(signed_amount)) / total_amount
                entry_fee += trade.fee
                amount += signed_amount
                continue
            close_amount = min(abs(amount), abs(signed_amount))
            fee_share = entry_fee * close_amount / abs(amount)
            if amount > 0:
                pnl = (trade.price - entry_price) * close_amount - fee_share - trade.fee
            else:
                pnl = (entry_price - trade.price) * close_amount - fee_share - trade.fee
            realized_pnls.append(pnl)
            remaining_amount = abs(amount) - close_amount
            if remaining_amount == 0:
                amount = Decimal("0")
                entry_price = Decimal("0")
                entry_fee = Decimal("0")
            else:
                amount += signed_amount
                entry_fee -= fee_share
        return realized_pnls

    def _empty_report(self) -> PerformanceReport:
        return PerformanceReport(
            initial_equity=Decimal("0"),
            final_equity=Decimal("0"),
            total_return=Decimal("0"),
            annual_return=Decimal("0"),
            volatility=0.0,
            max_drawdown=Decimal("0"),
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            trade_count=0,
            closed_trade_count=0,
            win_rate=Decimal("0"),
            profit_factor=Decimal("0"),
            gross_profit=Decimal("0"),
            gross_loss=Decimal("0"),
            average_win=Decimal("0"),
            average_loss=Decimal("0"),
            max_win=Decimal("0"),
            max_loss=Decimal("0"),
        )

    def _annual_return(self, total_return: Decimal, periods: int) -> Decimal:
        if periods <= 1:
            return Decimal("0")
        return Decimal(str((1 + float(total_return)) ** (self.periods_per_year / (periods - 1)) - 1)) #年化收益率 = (1 + 总收益率) ^ (一年有多少个周期 / 回测有多少个周期) - 1

    def _max_drawdown(self, equities: list[Decimal]) -> Decimal:
        peak = equities[0] #初始峰值
        max_drawdown = Decimal("0") #最大回撤初始值为0，因为还没有产生数据
        for equity in equities: #遍历我们提取出来的权益点纪录列表
            peak = max(peak, equity) #更新峰值（只升不降），找到权益最高点
            if peak:
                drawdown = equity / peak - Decimal("1") #计算当前回撤（可能为0，比如当前没回撤）
                max_drawdown = min(max_drawdown, drawdown)#更新最大回撤，最大回撤是负值，所以采用取最小反向得到最大值
        return max_drawdown #返回最大回撤的值（-）

    def _volatility(self, returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((item - mean_return) ** 2 for item in returns) / (len(returns) - 1)
        return sqrt(variance) * sqrt(self.periods_per_year)

    def _sharpe_ratio(self, returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((item - mean_return) ** 2 for item in returns) / (len(returns) - 1)
        volatility = sqrt(variance)
        if volatility == 0:
            return 0.0
        return mean_return / volatility * sqrt(self.periods_per_year)

    def _sortino_ratio(self, returns: list[float]) -> float:
        downside_returns = [item for item in returns if item < 0]
        if len(downside_returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns) if returns else 0.0
        downside_variance = sum(item**2 for item in downside_returns) / (len(downside_returns) - 1)
        downside_volatility = sqrt(downside_variance)
        if downside_volatility == 0:
            return 0.0
        return mean_return / downside_volatility * sqrt(self.periods_per_year)
