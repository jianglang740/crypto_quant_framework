from dataclasses import dataclass
from decimal import Decimal
from math import sqrt

from crypto_quant.strategy.base import Trade


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    total_return: Decimal
    max_drawdown: Decimal
    sharpe_ratio: float
    trade_count: int
    win_rate: Decimal
    gross_profit: Decimal
    gross_loss: Decimal


class PerformanceAnalyzer:
    def analyze(self, equity_curve: list[tuple[object, Decimal]], trades: list[Trade]) -> PerformanceReport:
        if not equity_curve:
            return PerformanceReport(
                total_return=Decimal("0"),
                max_drawdown=Decimal("0"),
                sharpe_ratio=0.0,
                trade_count=0,
                win_rate=Decimal("0"),
                gross_profit=Decimal("0"),
                gross_loss=Decimal("0"),
            )
        equities = [equity for _, equity in equity_curve]
        total_return = equities[-1] / equities[0] - Decimal("1") if equities[0] else Decimal("0")
        max_drawdown = self._max_drawdown(equities)
        sharpe_ratio = self._sharpe_ratio(equities)
        gross_profit = Decimal("0")
        gross_loss = Decimal("0")
        wins = 0
        paired = zip(trades[::2], trades[1::2], strict=False)
        for entry, exit_trade in paired:
            pnl = (exit_trade.price - entry.price) * entry.amount
            if entry.side.value == "sell":
                pnl = -pnl
            pnl -= entry.fee + exit_trade.fee
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                gross_loss += pnl
        closed_count = len(trades) // 2
        win_rate = Decimal(wins) / Decimal(closed_count) if closed_count else Decimal("0")
        return PerformanceReport(
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trade_count=len(trades),
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
        )

    def _max_drawdown(self, equities: list[Decimal]) -> Decimal:
        peak = equities[0]
        max_drawdown = Decimal("0")
        for equity in equities:
            peak = max(peak, equity)
            if peak:
                drawdown = equity / peak - Decimal("1")
                max_drawdown = min(max_drawdown, drawdown)
        return max_drawdown

    def _sharpe_ratio(self, equities: list[Decimal]) -> float:
        if len(equities) < 3:
            return 0.0
        returns = [float(equities[i] / equities[i - 1] - Decimal("1")) for i in range(1, len(equities)) if equities[i - 1]]
        if len(returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((item - mean_return) ** 2 for item in returns) / (len(returns) - 1)
        volatility = sqrt(variance)
        if volatility == 0:
            return 0.0
        return mean_return / volatility * sqrt(365)
