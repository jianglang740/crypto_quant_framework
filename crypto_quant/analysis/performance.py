from dataclasses import dataclass
from decimal import Decimal
from math import sqrt

from crypto_quant.strategy.base import Trade


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    initial_equity: Decimal
    final_equity: Decimal
    total_return: Decimal
    annual_return: Decimal
    volatility: float
    max_drawdown: Decimal
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    trade_count: int
    closed_trade_count: int
    win_rate: Decimal
    profit_factor: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    average_win: Decimal
    average_loss: Decimal
    max_win: Decimal
    max_loss: Decimal


class PerformanceAnalyzer:
    def __init__(self, periods_per_year: int = 365):
        self.periods_per_year = periods_per_year

    def analyze(self, equity_curve: list[tuple[object, Decimal]], trades: list[Trade]) -> PerformanceReport:
        if not equity_curve:
            return self._empty_report()
        equities = [equity for _, equity in equity_curve]
        returns = self.returns(equity_curve)
        initial_equity = equities[0]
        final_equity = equities[-1]
        total_return = final_equity / initial_equity - Decimal("1") if initial_equity else Decimal("0")
        annual_return = self._annual_return(total_return, len(equities))
        max_drawdown = self._max_drawdown(equities)
        volatility = self._volatility(returns)
        sharpe_ratio = self._sharpe_ratio(returns)
        sortino_ratio = self._sortino_ratio(returns)
        calmar_ratio = float(annual_return / abs(max_drawdown)) if max_drawdown else 0.0
        realized_pnls = self.realized_pnls(trades)
        gross_profit = sum((pnl for pnl in realized_pnls if pnl > 0), Decimal("0"))
        gross_loss = sum((pnl for pnl in realized_pnls if pnl <= 0), Decimal("0"))
        wins = [pnl for pnl in realized_pnls if pnl > 0]
        losses = [pnl for pnl in realized_pnls if pnl <= 0]
        closed_count = len(realized_pnls)
        win_rate = Decimal(len(wins)) / Decimal(closed_count) if closed_count else Decimal("0")
        profit_factor = gross_profit / abs(gross_loss) if gross_loss else Decimal("0")
        average_win = gross_profit / Decimal(len(wins)) if wins else Decimal("0")
        average_loss = gross_loss / Decimal(len(losses)) if losses else Decimal("0")
        max_win = max(wins) if wins else Decimal("0")
        max_loss = min(losses) if losses else Decimal("0")
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
        )

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
        return Decimal(str((1 + float(total_return)) ** (self.periods_per_year / (periods - 1)) - 1))

    def _max_drawdown(self, equities: list[Decimal]) -> Decimal:
        peak = equities[0]
        max_drawdown = Decimal("0")
        for equity in equities:
            peak = max(peak, equity)
            if peak:
                drawdown = equity / peak - Decimal("1")
                max_drawdown = min(max_drawdown, drawdown)
        return max_drawdown

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
