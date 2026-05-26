from decimal import Decimal
from pathlib import Path
from typing import Any

from bokeh.io import output_file, save
from bokeh.layouts import column, gridplot
from bokeh.models import ColumnDataSource, DataTable, HoverTool, NumeralTickFormatter, TableColumn
from bokeh.plotting import figure

from crypto_quant.analysis.performance import PerformanceAnalyzer, PerformanceReport
from crypto_quant.data.feed import DataFeed
from crypto_quant.enums import OrderSide
from crypto_quant.strategy.base import Trade


class BokehBacktestReport:
    def __init__(
        self,
        result: Any,
        data: DataFeed | None = None,
        title: str = "Backtest Report",
        analyzer: PerformanceAnalyzer | None = None,
    ):
        self.result = result
        self.data = data
        self.title = title
        self.analyzer = analyzer or PerformanceAnalyzer()
        self.metrics = self.analyzer.analyze(result.equity_curve, result.trades)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        output_file(path, title=self.title)
        save(self._layout())

    def _layout(self) -> Any:
        rows = [self._metrics_table(), self._strategy_table()]
        charts = [self._equity_curve(), self._drawdown_curve()]
        if self.data is not None:
            charts.append(self._price_with_trades())
        charts.append(self._trade_pnl_chart())
        rows.append(gridplot(charts, ncols=1, sizing_mode="stretch_width"))
        return column(*rows, sizing_mode="stretch_width")

    def _metrics_table(self) -> DataTable:
        data = {
            "metric": [
                "Initial Equity",
                "Final Equity",
                "Total Return",
                "Annual Return",
                "Volatility",
                "Max Drawdown",
                "Sharpe Ratio",
                "Sortino Ratio",
                "Calmar Ratio",
                "Trade Count",
                "Closed Trade Count",
                "Win Rate",
                "Profit Factor",
                "Gross Profit",
                "Gross Loss",
                "Average Win",
                "Average Loss",
                "Max Win",
                "Max Loss",
            ],
            "value": [
                self._decimal(self.metrics.initial_equity),
                self._decimal(self.metrics.final_equity),
                self._percent(self.metrics.total_return),
                self._percent(self.metrics.annual_return),
                self._float(self.metrics.volatility),
                self._percent(self.metrics.max_drawdown),
                self._float(self.metrics.sharpe_ratio),
                self._float(self.metrics.sortino_ratio),
                self._float(self.metrics.calmar_ratio),
                str(self.metrics.trade_count),
                str(self.metrics.closed_trade_count),
                self._percent(self.metrics.win_rate),
                self._decimal(self.metrics.profit_factor),
                self._decimal(self.metrics.gross_profit),
                self._decimal(self.metrics.gross_loss),
                self._decimal(self.metrics.average_win),
                self._decimal(self.metrics.average_loss),
                self._decimal(self.metrics.max_win),
                self._decimal(self.metrics.max_loss),
            ],
        }
        source = ColumnDataSource(data)
        columns = [TableColumn(field="metric", title="Metric"), TableColumn(field="value", title="Value")]
        return DataTable(source=source, columns=columns, height=420, sizing_mode="stretch_width", index_position=None)

    def _strategy_table(self) -> DataTable:
        strategy_trades = getattr(self.result, "strategy_trades", None)
        if not strategy_trades:
            source = ColumnDataSource({"strategy": ["total"], "trade_count": [len(self.result.trades)]})
        else:
            source = ColumnDataSource(
                {
                    "strategy": list(strategy_trades.keys()),
                    "trade_count": [len(trades) for trades in strategy_trades.values()],
                }
            )
        columns = [TableColumn(field="strategy", title="Strategy"), TableColumn(field="trade_count", title="Trade Count")]
        return DataTable(source=source, columns=columns, height=120, sizing_mode="stretch_width", index_position=None)

    def _equity_curve(self) -> Any:
        timestamps = [timestamp for timestamp, _ in self.result.equity_curve]
        equities = [float(equity) for _, equity in self.result.equity_curve]
        initial = equities[0] if equities else 0.0
        returns = [(equity / initial - 1) if initial else 0.0 for equity in equities]
        source = ColumnDataSource({"datetime": timestamps, "equity": equities, "return": returns})
        plot = figure(title="Equity Curve", x_axis_type="datetime", height=320, tools="pan,wheel_zoom,box_zoom,reset,save")
        plot.line("datetime", "equity", source=source, line_width=2, color="#1f77b4")
        plot.add_tools(
            HoverTool(
                tooltips=[("Time", "@datetime{%F %T}"), ("Equity", "@equity{0,0.00}"), ("Return", "@return{0.00%}")],
                formatters={"@datetime": "datetime"},
                mode="vline",
            )
        )
        return plot

    def _drawdown_curve(self) -> Any:
        drawdowns = self.analyzer.drawdowns(self.result.equity_curve)
        source = ColumnDataSource(
            {
                "datetime": [timestamp for timestamp, _ in drawdowns],
                "drawdown": [float(drawdown) for _, drawdown in drawdowns],
            }
        )
        plot = figure(title="Drawdown", x_axis_type="datetime", height=260, tools="pan,wheel_zoom,box_zoom,reset,save")
        plot.line("datetime", "drawdown", source=source, line_width=2, color="#d62728")
        plot.add_tools(
            HoverTool(
                tooltips=[("Time", "@datetime{%F %T}"), ("Drawdown", "@drawdown{0.00%}")],
                formatters={"@datetime": "datetime"},
                mode="vline",
            )
        )
        plot.yaxis.formatter = NumeralTickFormatter(format="0.00%")
        return plot

    def _price_with_trades(self) -> Any:
        if self.data is None:
            raise RuntimeError("data is required")
        price_source = ColumnDataSource(
            {
                "datetime": [bar.datetime for bar in self.data.bars],
                "close": [float(bar.close) for bar in self.data.bars],
            }
        )
        plot = figure(title="Price and Trades", x_axis_type="datetime", height=360, tools="pan,wheel_zoom,box_zoom,reset,save")
        plot.line("datetime", "close", source=price_source, line_width=2, color="#444444", legend_label="Close")
        buy_source = self._trade_source(OrderSide.BUY)
        sell_source = self._trade_source(OrderSide.SELL)
        if buy_source.data["datetime"]:
            plot.scatter("datetime", "price", source=buy_source, marker="triangle", size=10, color="#2ca02c", legend_label="Buy")
        if sell_source.data["datetime"]:
            plot.scatter("datetime", "price", source=sell_source, marker="inverted_triangle", size=10, color="#d62728", legend_label="Sell")
        plot.add_tools(
            HoverTool(
                tooltips=[("Time", "@datetime{%F %T}"), ("Price", "@price{0,0.00}"), ("Amount", "@amount{0,0.####}"), ("Side", "@side")],
                formatters={"@datetime": "datetime"},
                renderers=plot.renderers[1:],
            )
        )
        plot.legend.click_policy = "hide"
        return plot

    def _trade_pnl_chart(self) -> Any:
        pnls = self.analyzer.realized_pnls(self.result.trades)
        source = ColumnDataSource(
            {
                "index": list(range(1, len(pnls) + 1)),
                "pnl": [float(pnl) for pnl in pnls],
                "color": ["#2ca02c" if pnl > 0 else "#d62728" for pnl in pnls],
            }
        )
        plot = figure(title="Closed Trade PnL", height=280, tools="pan,wheel_zoom,box_zoom,reset,save")
        plot.vbar(x="index", top="pnl", width=0.8, source=source, color="color")
        plot.add_tools(HoverTool(tooltips=[("Trade", "@index"), ("PnL", "@pnl{0,0.00}")]))
        return plot

    def _trade_source(self, side: OrderSide) -> ColumnDataSource:
        trades: list[Trade] = [trade for trade in self.result.trades if trade.side == side]
        return ColumnDataSource(
            {
                "datetime": [trade.traded_at for trade in trades],
                "price": [float(trade.price) for trade in trades],
                "amount": [float(trade.amount) for trade in trades],
                "side": [trade.side.value for trade in trades],
            }
        )

    def _decimal(self, value: Decimal) -> str:
        return f"{value:.6f}"

    def _percent(self, value: Decimal) -> str:
        return f"{value * Decimal('100'):.2f}%"

    def _float(self, value: float) -> str:
        return f"{value:.6f}"
