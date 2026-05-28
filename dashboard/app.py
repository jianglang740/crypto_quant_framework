from __future__ import annotations

import html
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from bokeh.embed import file_html
from bokeh.models import ColumnDataSource, HoverTool, NumeralTickFormatter
from bokeh.plotting import figure
from bokeh.resources import CDN
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from crypto_quant.config import MySQLConfig
from crypto_quant.database import TradingRepository, create_mysql_engine, create_session_factory
from crypto_quant.database.models import AccountSnapshot, EquityCurve, Kline, OrderRecord, PositionSnapshot, StrategyRun, TradeRecord


APP_DIR = Path(__file__).resolve().parent
BEIJING_OFFSET = timedelta(hours=8)


@dataclass(frozen=True)
class MarketContext:
    exchange: str
    symbol: str
    timeframe: str



@dataclass(frozen=True)
class DashboardData:
    runs: list[StrategyRun]
    selected_run: StrategyRun | None
    orders: list[OrderRecord]
    trades: list[TradeRecord]
    equity_curve: list[EquityCurve]
    account_snapshots: list[AccountSnapshot]
    position_snapshots: list[PositionSnapshot]
    market_klines: list[Kline]
    error: str | None = None


def main() -> None:
    st.set_page_config(page_title="whale 的量化仪表盘", page_icon="📈", layout="wide")
    load_css()

    st.sidebar.title("whale 仪表盘")
    page_options = {
        "首页": "🏠 首页",
        "实盘速览": "📡 实盘速览",
        "回测报告": "📊 回测报告",
        "关于我们": "ℹ️ 关于我们",
    }
    nav_light = pixel_traffic_light_html("green", "xs")
    st.sidebar.markdown(f'<div class="sidebar-nav-label"><span>导航</span>{nav_light}</div>', unsafe_allow_html=True)
    selected_page = st.sidebar.radio("导航", list(page_options), format_func=page_options.get, label_visibility="collapsed")
    st.sidebar.markdown('<div class="sidebar-note">只读展示页面，不执行下单、不修改数据库。</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f'<div class="sidebar-whale">{pixel_whale_html("md")}</div>', unsafe_allow_html=True)

    if selected_page == "首页":
        render_home()
        return

    data = load_dashboard_data()
    if data.error is not None:
        render_database_error(data.error)
        return

    if selected_page == "实盘速览":
        render_live_overview(data)
    elif selected_page == "回测报告":
        render_backtest_report(data)
    else:
        render_about()


def load_css() -> None:
    css_path = APP_DIR / "style.css"
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE", "crypto_quant"),
    )


@st.cache_data(ttl=60)
def load_dashboard_data(selected_run_id: str | None = None) -> DashboardData:
    try:
        engine = create_mysql_engine(mysql_config_from_env())
        Session = create_session_factory(engine)
        with Session() as session:
            repository = TradingRepository(session)
            runs = repository.list_runs(limit=50)
            selected_run = choose_run(runs, selected_run_id)
            if selected_run is None:
                return DashboardData([], None, [], [], [], [], [], [])
            market_context = market_context_from_run(selected_run)
            equity_curve = repository.get_equity_curve(selected_run.run_id)
            market_klines = load_backtest_klines(session, market_context, equity_curve) if selected_run.run_type == "backtest" else load_recent_klines(session, market_context, days=5)
            return DashboardData(
                runs=runs,
                selected_run=selected_run,
                orders=repository.get_orders(selected_run.run_id),
                trades=repository.get_trades(selected_run.run_id),
                equity_curve=equity_curve,
                account_snapshots=repository.get_account_snapshots(selected_run.run_id),
                position_snapshots=repository.get_position_snapshots(selected_run.run_id),
                market_klines=market_klines,
            )
    except (SQLAlchemyError, OSError, ValueError) as exc:
        return DashboardData([], None, [], [], [], [], [], [], error=str(exc))


def load_backtest_klines(session, market_context: MarketContext, equity_curve: list[EquityCurve]) -> list[Kline]:
    if not equity_curve:
        return []
    start_time = equity_curve[0].timestamp
    end_time = equity_curve[-1].timestamp
    statement = (
        select(Kline)
        .where(Kline.exchange == market_context.exchange)
        .where(Kline.symbol == market_context.symbol)
        .where(Kline.timeframe == market_context.timeframe)
        .where(Kline.open_time >= start_time)
        .where(Kline.open_time <= end_time)
        .order_by(Kline.open_time.asc())
    )
    return list(session.scalars(statement).all())



def load_recent_klines(session, market_context: MarketContext, days: int) -> list[Kline]:
    latest_time = session.scalar(
        select(Kline.open_time)
        .where(Kline.exchange == market_context.exchange)
        .where(Kline.symbol == market_context.symbol)
        .where(Kline.timeframe == market_context.timeframe)
        .order_by(Kline.open_time.desc())
        .limit(1)
    )
    if latest_time is None:
        return []
    start_time = latest_time - timedelta(days=days)
    statement = (
        select(Kline)
        .where(Kline.exchange == market_context.exchange)
        .where(Kline.symbol == market_context.symbol)
        .where(Kline.timeframe == market_context.timeframe)
        .where(Kline.open_time >= start_time)
        .order_by(Kline.open_time.asc())
    )
    return list(session.scalars(statement).all())


def market_context_from_run(run: StrategyRun) -> MarketContext:
    config = parse_json_object(run.config)
    return MarketContext(
        exchange=config.get("exchange", "binance"),
        symbol=first_symbol(run.symbols) or config.get("symbol", "ETH/USDT"),
        timeframe=run.timeframe or config.get("timeframe", "5m"),
    )



def first_symbol(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, list) and parsed:
        return str(parsed[0])
    if isinstance(parsed, str):
        return parsed
    return value



def choose_run(runs: list[StrategyRun], selected_run_id: str | None) -> StrategyRun | None:
    if not runs:
        return None
    if selected_run_id is None:
        return runs[0]
    return next((run for run in runs if run.run_id == selected_run_id), runs[0])


def pixel_whale_html(size: str = "md") -> str:
    whale = [
        "................s....................",
        "...............sss...................",
        "..............ss.ss..................",
        "...............sss...................",
        "................s....................",
        ".....................................",
        ".................ooo.................",
        "............ooooo...oo...........ooo.",
        ".........ooo.dddddd...oo........bbbo.",
        ".......oo.ddbbbbbbbbd...oo.....bbbo..",
        ".....oo.ddbbbbbbbbbbbbd..o....bbbo...",
        "....o.ddbbbbbbbbbbbbbbbd.o..oobbo....",
        "....o.dbbbbbbbbbbbbbbbbbddo.bobo.....",
        "....o.dbbbbbbbbbbbbbbbbbbbbbbdbo.....",
        "....odbbxxbbbblbbbbbbbbbbbbdoobbo....",
        "....o.dbbbbbbbbbbpbbbbbbbdo..bbbbo...",
        ".....o.dbbbbbbbbbbbbbbbbbdo...bbbbo..",
        "......oo.dwwwwwwwwwbbbdo........bbbo.",
        "........ooooooooooooooo.........oooo.",
    ]
    pixels = "".join(
        f'<span class="pixel {cell}"></span>' if cell != "." else '<span class="pixel"></span>'
        for row in whale
        for cell in row
    )
    return f'<div class="pixel-whale-icon" data-size="{html.escape(size)}" aria-label="卡通像素风鲸鱼图标"><div class="pixel-whale-grid">{pixels}</div></div>'



def pixel_traffic_light_html(state: str = "red", size: str = "sm") -> str:
    traffic_light = {
        "red": [
            "......oooooooooooooooooooooooooooo....",
            "....ooommmmmmmmmmmmmmmmmmmmmmmmmmooo..",
            "...oomdddddddddddddddddddddddddddmmoo.",
            "...odddrrrrrrrdddyyyyyydddgggggggddmo.",
            "..oomdRRqqqqRRdddyyyyyydddggggggggdmoo",
            "..ommdRRqqqqRRdddyyyyyydddggggggggdmmo",
            "..ommdRRqqqqRRdddyyyyyydddggggggggdmmo",
            "..oomdRRqqqqRRdddyyyyyydddggggggggdmoo",
            "...odddrrrrrrrdddyyyyyydddgggggggddmo.",
            "...oomdddddddddddddddddddddddddddmmoo.",
            "....ooommmmmmmmmmmmmmmmmmmmmmmmmmooo..",
            "......oooooooooooooooooooooooooooo....",
            ".............oo..........oo...........",
        ],
        "yellow": [
            "......oooooooooooooooooooooooooooo....",
            "....ooommmmmmmmmmmmmmmmmmmmmmmmmmooo..",
            "...oomdddddddddddddddddddddddddddmmoo.",
            "...odddrrrrrrrdddyyyyyydddgggggggddmo.",
            "..oomdrrrrrrrrddduYYYYudddggggggggdmoo",
            "..ommdrrrrrrrrddduYYYYudddggggggggdmmo",
            "..ommdrrrrrrrrddduYYYYudddggggggggdmmo",
            "..oomdrrrrrrrrddduYYYYudddggggggggdmoo",
            "...odddrrrrrrrdddyyyyyydddgggggggddmo.",
            "...oomdddddddddddddddddddddddddddmmoo.",
            "....ooommmmmmmmmmmmmmmmmmmmmmmmmmooo..",
            "......oooooooooooooooooooooooooooo....",
            ".............oo..........oo...........",
        ],
        "green": [
            "......oooooooooooooooooooooooooooo....",
            "....ooommmmmmmmmmmmmmmmmmmmmmmmmmooo..",
            "...oomdddddddddddddddddddddddddddmmoo.",
            "...odddrrrrrrrdddyyyyyydddgggggggddmo.",
            "..oomdrrrrrrrrdddyyyyyydddGGvvvvGGdmoo",
            "..ommdrrrrrrrrdddyyyyyydddGGvvvvGGdmmo",
            "..ommdrrrrrrrrdddyyyyyydddGGvvvvGGdmmo",
            "..oomdrrrrrrrrdddyyyyyydddGGvvvvGGdmoo",
            "...odddrrrrrrrdddyyyyyydddgggggggddmo.",
            "...oomdddddddddddddddddddddddddddmmoo.",
            "....ooommmmmmmmmmmmmmmmmmmmmmmmmmooo..",
            "......oooooooooooooooooooooooooooo....",
            ".............oo..........oo...........",
        ],
    }
    selected_state = state if state in traffic_light else "red"
    pixels = "".join(
        f'<span class="pixel {cell}"></span>' if cell != "." else '<span class="pixel"></span>'
        for row in traffic_light[selected_state]
        for cell in row
    )
    return f'<div class="pixel-traffic-light" data-size="{html.escape(size)}" data-state="{html.escape(selected_state)}" aria-label="红色像素红绿灯状态图标"><div class="pixel-traffic-grid">{pixels}</div></div>'



def render_home() -> None:
    whale_icon = pixel_whale_html("sm")
    read_only_light = pixel_traffic_light_html("red", "sm")
    candle_specs = [
        (46, 68, 36, 76),
        (70, 96, 58, 106),
        (98, 132, 88, 144),
        (134, 166, 122, 178),
        (164, 138, 128, 176),
        (136, 104, 94, 148),
        (104, 82, 72, 116),
        (84, 112, 76, 124),
        (114, 148, 104, 160),
        (150, 128, 118, 162),
        (126, 94, 84, 138),
        (96, 78, 68, 108),
        (80, 58, 48, 90),
        (60, 38, 28, 70),
        (40, 28, 18, 52),
        (30, 46, 22, 58),
        (48, 26, 18, 58),
        (28, 16, 8, 40),
    ]
    candles = "".join(
        candle_html(open_y, close_y, high_y, low_y)
        for open_y, close_y, high_y, low_y in candle_specs
    )
    st.markdown(
        f"""
        <div class="dashboard-hero">
            <div class="hero-card">
                <div class="hero-kicker">{whale_icon}<span>PERSONAL QUANT DASHBOARD</span></div>
                <div class="hero-main-title">whale 的量化仪表盘指南</div>
                <div class="hero-message">
                    <p>你好，我是 <span class="highlight">whale</span>。</p>
                    <p>这里记录我的 <span class="highlight">量化研究</span>、回测复盘和策略运行观察。</p>
                    <p>它不是交易控制台，而是一个从数据库读取结果的只读展示窗口。</p>
                </div>
                <div class="home-entry-grid">
                    <div class="home-entry-card"><span>📡</span><strong>实盘速览</strong><small>账户快照、持仓、订单成交</small></div>
                    <div class="home-entry-card"><span>📊</span><strong>回测报告</strong><small>收益回撤、交易统计、买卖点</small></div>
                </div>
                <div class="home-note">策略运行、参数修改和交易控制仍然通过代码管理，仪表盘只负责展示与复盘。</div>
            </div>
            <div class="visual-card">
                <div class="visual-stack">
                    <div class="read-only-badge">{read_only_light}<span>READ ONLY</span></div>
                    <div class="laptop">
                        <div class="laptop-screen">
                            <div class="chart-toolbar"><span>ETH/USDT · 5m</span><span>Backtest View</span></div>
                            <div class="candlestick-chart">
                                <div class="chart-grid"></div>
                                <div class="price-axis"><span>3,260</span><span>3,180</span><span>3,100</span></div>
                                <div class="candle-layer">{candles}</div>
                            </div>
                        </div>
                        <div class="laptop-base"></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def candle_html(open_y: int, close_y: int, high_y: int, low_y: int) -> str:
    direction = "up" if close_y < open_y else "down"
    body_top = min(open_y, close_y)
    body_height = max(abs(close_y - open_y), 4)
    wick_height = low_y - high_y
    return (
        f'<div class="candle {direction}" '
        f'style="--high:{high_y}px; --wick:{wick_height}px; --body-top:{body_top}px; --body:{body_height}px;">'
        f'</div>'
    )



def render_database_error(error: str) -> None:
    st.markdown('<div class="section-title">数据库连接暂不可用</div>', unsafe_allow_html=True)
    st.warning("仪表盘已经启动，但没有读取到 MySQL 数据。请确认本地数据库、账号密码和环境变量配置。")
    st.code(error)
    st.markdown(
        """
        可选环境变量：

        ```bash
        export CRYPTO_QUANT_MYSQL_HOST=127.0.0.1
        export CRYPTO_QUANT_MYSQL_PORT=3306
        export CRYPTO_QUANT_MYSQL_USERNAME=root
        export CRYPTO_QUANT_MYSQL_PASSWORD=你的密码
        export CRYPTO_QUANT_MYSQL_DATABASE=crypto_quant
        ```
        """
    )


def render_run_selector(runs: list[StrategyRun], key: str) -> StrategyRun | None:
    if not runs:
        st.info("数据库里还没有 strategy_runs 记录。")
        return None
    labels = [run_label(run) for run in runs]
    st.markdown('<div class="selector-hint">请选择要查看的运行记录</div>', unsafe_allow_html=True)
    selected_label = st.selectbox("运行记录", labels, key=key, label_visibility="collapsed")
    return runs[labels.index(selected_label)]


def render_live_overview(data: DashboardData) -> None:
    enable_auto_refresh(60)
    st.markdown('<div class="section-subtitle">Live / Dry Run Overview</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">实盘速览</div>', unsafe_allow_html=True)
    st.caption("页面每 60 秒自动刷新一次，数据缓存最多保留 60 秒。")
    live_runs = [run for run in data.runs if run.run_type in {"live", "dry_run", "testnet"}]
    selected_run = render_run_selector(live_runs, "live_run_selector")
    if selected_run is None:
        return
    data = load_dashboard_data(selected_run.run_id)
    selected_run = data.selected_run or selected_run
    latest_account = data.account_snapshots[-1] if data.account_snapshots else None
    latest_positions = latest_position_rows(data.position_snapshots, getattr(latest_account, "timestamp", None))
    account_df = records_to_dataframe(data.account_snapshots)
    market_df = records_to_dataframe(data.market_klines)
    market_context = market_context_from_run(selected_run)
    metrics = calculate_live_metrics(selected_run, data)
    snapshot_status = calculate_snapshot_status(latest_account)

    render_metric_grid(
        [
            ("初始资金", format_decimal(selected_run.initial_cash)),
            ("当前权益", format_decimal(getattr(latest_account, "equity", None))),
            ("最大回撤", format_percent(metrics["max_drawdown"])),
            ("胜率", format_percent(metrics["win_rate"])),
            ("夏普", format_float(metrics["sharpe"])),
            ("成交次数", metrics["trade_count"]),
            ("当前持仓", len(latest_positions)),
            ("运行状态", selected_run.status),
            ("最后快照", format_datetime(snapshot_status["timestamp"])),
            ("快照延迟", format_duration(snapshot_status["age_seconds"])),
            ("快照状态", snapshot_status["status"]),
        ]
    )

    render_run_info(selected_run)

    if not account_df.empty and {"timestamp", "equity"}.issubset(account_df.columns):
        chart_df = account_df.set_index("timestamp")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 权益曲线")
            render_bokeh_chart(bokeh_equity_chart(chart_df), height=360)
        with col2:
            st.markdown("### 回撤曲线")
            render_bokeh_chart(bokeh_drawdown_chart(chart_df), height=360)

        col3, col4 = st.columns(2)
        with col3:
            st.markdown("### 可用余额")
            render_bokeh_chart(bokeh_multi_line_chart(chart_df, ["available"], "可用余额"), height=340)
        with col4:
            st.markdown("### 未实现盈亏")
            render_bokeh_chart(bokeh_multi_line_chart(chart_df, ["unrealized_pnl"], "未实现盈亏"), height=340)

    if not market_df.empty and {"open_time", "close"}.issubset(market_df.columns):
        st.markdown(f"### {market_context.symbol} 最近 5 天行情")
        render_bokeh_chart(bokeh_market_chart(market_df, market_context), height=400)
    else:
        st.info(f"暂未读取到 {market_context.exchange} {market_context.symbol} {market_context.timeframe} K 线数据，可以先运行 dashboard/import_dashboard_klines.py 入库。")

    st.markdown("### 当前持仓快照")
    st.dataframe(pd.DataFrame(latest_positions), use_container_width=True, hide_index=True)

    col5, col6 = st.columns(2)
    with col5:
        st.markdown("### 最近订单")
        st.dataframe(records_to_dataframe(data.orders[-50:]), use_container_width=True, hide_index=True)
    with col6:
        st.markdown("### 最近成交")
        st.dataframe(records_to_dataframe(data.trades[-50:]), use_container_width=True, hide_index=True)


def render_backtest_report(data: DashboardData) -> None:
    st.markdown('<div class="section-subtitle">Backtest Report</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">回测报告</div>', unsafe_allow_html=True)
    backtest_runs = [run for run in data.runs if run.run_type == "backtest"]
    selected_run = render_run_selector(backtest_runs, "backtest_run_selector")
    if selected_run is None:
        return
    data = load_dashboard_data(selected_run.run_id)
    equity_df = records_to_dataframe(data.equity_curve)
    trade_df = build_backtest_trade_dataframe(data.trades)
    order_df = build_backtest_order_dataframe(data.orders)
    market_df = records_to_dataframe(data.market_klines)
    market_context = market_context_from_run(selected_run)
    metrics = calculate_backtest_metrics(selected_run, data)
    trade_stats = calculate_backtest_trade_stats(data.trades)

    render_metric_grid(
        [
            ("初始资金", format_decimal(metrics["initial_equity"])),
            ("最终权益", format_decimal(metrics["final_equity"])),
            ("收益率", format_percent(metrics["total_return"])),
            ("最大回撤", format_percent(metrics["max_drawdown"])),
            ("胜率", format_percent(metrics["win_rate"])),
            ("夏普", format_float(metrics["sharpe"])),
            ("订单数", len(data.orders)),
            ("成交数", len(data.trades)),
        ]
    )

    st.markdown("### 交易统计")
    render_metric_grid(
        [
            ("盈利平仓", trade_stats["win_count"]),
            ("亏损平仓", trade_stats["loss_count"]),
            ("平均盈利", format_decimal(trade_stats["avg_win"])),
            ("平均亏损", format_decimal(trade_stats["avg_loss"])),
            ("最大盈利", format_decimal(trade_stats["max_win"])),
            ("最大亏损", format_decimal(trade_stats["max_loss"])),
            ("手续费合计", format_decimal(trade_stats["total_fee"])),
            ("盈亏比因子", format_float(trade_stats["profit_factor"])),
        ]
    )

    render_run_info(selected_run)
    render_backtest_config(selected_run)

    if not equity_df.empty and {"timestamp", "equity"}.issubset(equity_df.columns):
        chart_df = equity_df.set_index("timestamp")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 权益曲线")
            render_bokeh_chart(bokeh_equity_chart(chart_df), height=360)
        with col2:
            st.markdown("### 回撤曲线")
            render_bokeh_chart(bokeh_drawdown_chart(chart_df), height=360)

        fund_df = build_backtest_fund_dataframe(chart_df, metrics["initial_equity"])
        st.markdown("### 资金变化")
        render_bokeh_chart(bokeh_multi_line_chart(fund_df, ["equity", "net_pnl", "drawdown_amount"], "资金变化"), height=360)
    else:
        st.info("这条回测记录暂未读取到 equity_curve 数据。")

    if not market_df.empty and {"open_time", "close"}.issubset(market_df.columns):
        st.markdown(f"### {market_context.symbol} 回测区间行情")
        render_bokeh_chart(bokeh_market_chart(market_df, market_context, data.trades, title_suffix="回测区间行情"), height=400)
    else:
        st.info(f"暂未读取到 {market_context.exchange} {market_context.symbol} {market_context.timeframe} 回测区间 K 线数据，可以先运行 dashboard/import_dashboard_klines.py 入库。")

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("### 订单")
        st.dataframe(order_df, use_container_width=True, hide_index=True)
    with col4:
        st.markdown("### 成交")
        st.dataframe(trade_df, use_container_width=True, hide_index=True)

    st.markdown("### 运行记录")
    st.dataframe(records_to_dataframe([selected_run]), use_container_width=True, hide_index=True)


def render_backtest_config(run: StrategyRun) -> None:
    config = parse_json_object(run.config)
    if not config:
        return
    keys = ["purpose", "csv", "symbol", "timeframe", "threshold", "take_profit_rate", "stop_loss_rate", "position_ratio", "leverage"]
    rows = [{"参数": key, "值": config[key]} for key in keys if key in config]
    if rows:
        st.markdown("### 回测配置")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)



def render_run_info(run: StrategyRun) -> None:
    config = parse_json_object(run.config)
    symbols = run.symbols or config.get("symbol") or "-"
    timeframe = run.timeframe or config.get("timeframe") or "-"
    st.markdown("### 当前运行策略信息")
    st.markdown(
        f"""
        <div class="panel-card muted-text">
        <b>运行名称：</b>{run.name}<br>
        <b>运行 ID：</b>{run.run_id}<br>
        <b>策略名称：</b>{run.strategy_name or "-"}<br>
        <b>运行类型：</b>{run.run_type}<br>
        <b>交易模式：</b>{run.trading_mode}<br>
        <b>交易对：</b>{symbols}<br>
        <b>K 线周期：</b>{timeframe}<br>
        <b>开始时间：</b>{format_datetime(run.started_at)}<br>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_about() -> None:
    st.markdown('<div class="section-subtitle">About</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">关于我们</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="panel-card muted-text">
        这个仪表盘是 crypto_quant_framework 的只读展示层，用来观察回测、dry_run、testnet 和后续实盘运行结果。
        <br><br>
        当前版本不提供下单、撤单、启动策略、停止策略或参数修改能力。策略研究、运行管理和交易控制仍然通过代码完成，仪表盘只负责展示结果和辅助复盘。
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_grid(items: list[tuple[str, Any]]) -> None:
    cards = "".join(metric_card_html(label, value) for label, value in items)
    st.markdown(f'<div class="metric-grid">{cards}</div>', unsafe_allow_html=True)



def enable_auto_refresh(seconds: int) -> None:
    components.html(
        f"""
        <script>
        setTimeout(function() {{ window.parent.location.reload(); }}, {seconds * 1000});
        </script>
        """,
        height=0,
    )



def metric_card_html(label: str, value: Any) -> str:
    label_text = html.escape(str(label))
    value_text = html.escape(str(value))
    classes = ["metric-card"]
    if label in {"当前权益", "最终权益", "收益率", "最大回撤", "胜率", "当前持仓", "运行状态", "快照状态"}:
        classes.append("metric-card-primary")
    if label == "快照状态":
        status_value = str(value)
        traffic_state = snapshot_status_traffic_state(status_value)
        traffic_light = pixel_traffic_light_html(traffic_state, "xs")
        value_html = f'<span class="status-badge status-badge-with-light {snapshot_status_class(status_value)}"><span>{value_text}</span>{traffic_light}</span>'
    else:
        value_html = value_text
    return f'<div class="{" ".join(classes)}"><div class="metric-label">{label_text}</div><div class="metric-value">{value_html}</div></div>'



def snapshot_status_class(value: str) -> str:
    return {
        "正常": "status-ok",
        "延迟": "status-delay",
        "疑似停止": "status-stopped",
        "无快照": "status-empty",
    }.get(value, "status-empty")


def snapshot_status_traffic_state(value: str) -> str:
    return {
        "正常": "green",
        "延迟": "yellow",
        "疑似停止": "red",
        "无快照": "red",
    }.get(value, "red")


def run_label(run: StrategyRun) -> str:
    return f"{format_datetime(run.created_at)} | {run.run_type} | {run.name} | {run.run_id}"


def to_beijing_time(value: Any) -> Any:
    if isinstance(value, datetime):
        return value + BEIJING_OFFSET
    return value


def records_to_dataframe(records: list[Any]) -> pd.DataFrame:
    rows = [record_to_dict(record) for record in records]
    return pd.DataFrame(rows)


def record_to_dict(record: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        if isinstance(value, Decimal):
            result[column.name] = float(value)
        else:
            result[column.name] = to_beijing_time(value)
    return result


def build_backtest_order_dataframe(orders: list[OrderRecord]) -> pd.DataFrame:
    rows = []
    for order in orders:
        rows.append(
            {
                "时间": to_beijing_time(order.created_at),
                "交易对": order.symbol,
                "方向": order.side,
                "类型": order.order_type,
                "状态": order.status,
                "数量": float(order.amount),
                "成交均价": float(order.average) if order.average is not None else None,
                "已成交": float(order.filled),
                "只减仓": order.reduce_only,
            }
        )
    return pd.DataFrame(rows)



def build_backtest_trade_dataframe(trades: list[TradeRecord]) -> pd.DataFrame:
    realized_pnls = realized_pnls_by_trade_id(trades)
    rows = []
    for trade in sorted(trades, key=lambda item: item.traded_at):
        rows.append(
            {
                "时间": to_beijing_time(trade.traded_at),
                "交易对": trade.symbol,
                "方向": trade.side,
                "数量": float(trade.amount),
                "价格": float(trade.price),
                "手续费": float(trade.fee or 0),
                "平仓盈亏": float(realized_pnls[trade.id]) if trade.id in realized_pnls else None,
            }
        )
    return pd.DataFrame(rows)



def parse_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return result if isinstance(result, dict) else {}



def latest_position_rows(snapshots: list[PositionSnapshot], latest_account_time: datetime | None = None) -> list[dict[str, Any]]:
    if latest_account_time is not None:
        snapshots = [snapshot for snapshot in snapshots if snapshot.timestamp == latest_account_time]
    latest: dict[tuple[str, str, str | None], PositionSnapshot] = {}
    for snapshot in snapshots:
        key = (snapshot.symbol, snapshot.side, snapshot.strategy_name)
        latest[key] = snapshot
    return [record_to_dict(snapshot) for snapshot in latest.values()]


def render_bokeh_chart(plot, height: int) -> None:
    html = file_html(plot, CDN, plot.title.text or "Bokeh Chart")
    components.html(html, height=height, scrolling=False)


def bokeh_equity_chart(df: pd.DataFrame):
    chart_df = df.reset_index().rename(columns={"index": "timestamp"})
    source = ColumnDataSource(chart_df)
    plot = base_time_series_figure("账户权益曲线", height=320)
    plot.line("timestamp", "equity", source=source, line_width=2.5, color="#4fc3f7", legend_label="equity")
    plot.add_tools(
        HoverTool(
            tooltips=[("时间", "@timestamp{%F %T}"), ("权益", "@equity{0,0.00}")],
            formatters={"@timestamp": "datetime"},
            mode="vline",
        )
    )
    plot.legend.location = "top_left"
    return plot


def bokeh_drawdown_chart(df: pd.DataFrame):
    chart_df = df.reset_index().rename(columns={"index": "timestamp"})
    chart_df["drawdown"] = calculate_drawdown_series(chart_df["equity"])
    source = ColumnDataSource(chart_df)
    plot = base_time_series_figure("回撤曲线", height=320)
    plot.line("timestamp", "drawdown", source=source, line_width=2.5, color="#fb7185", legend_label="drawdown")
    plot.yaxis.formatter = NumeralTickFormatter(format="0.00%")
    plot.add_tools(
        HoverTool(
            tooltips=[("时间", "@timestamp{%F %T}"), ("回撤", "@drawdown{0.00%}")],
            formatters={"@timestamp": "datetime"},
            mode="vline",
        )
    )
    plot.legend.location = "bottom_left"
    return plot


def bokeh_multi_line_chart(df: pd.DataFrame, columns: list[str], title: str):
    chart_df = df.reset_index().rename(columns={"index": "timestamp"})
    existing_columns = [column for column in columns if column in chart_df.columns]
    source = ColumnDataSource(chart_df)
    plot = base_time_series_figure(title, height=300)
    colors = ["#4ade80", "#fbbf24", "#a78bfa", "#4fc3f7"]
    renderers = []
    tooltips = [("时间", "@timestamp{%F %T}")]
    for index, column in enumerate(existing_columns):
        renderer = plot.line(
            "timestamp",
            column,
            source=source,
            line_width=2.2,
            color=colors[index % len(colors)],
            legend_label=column,
        )
        renderers.append(renderer)
        tooltips.append((column, f"@{column}{{0,0.00}}"))
    if renderers:
        plot.add_tools(HoverTool(tooltips=tooltips, formatters={"@timestamp": "datetime"}, mode="vline", renderers=renderers))
    plot.legend.location = "top_left"
    plot.legend.click_policy = "hide"
    return plot


def bokeh_market_chart(df: pd.DataFrame, market_context: MarketContext, trades: list[TradeRecord] | None = None, title_suffix: str = "最近 5 天行情"):
    chart_df = df.copy().sort_values("open_time")
    source = ColumnDataSource(chart_df)
    plot = base_time_series_figure(f"{market_context.symbol} {market_context.timeframe} {title_suffix}", height=360)
    price_renderer = plot.line("open_time", "close", source=source, line_width=2.4, color="#4fc3f7", alpha=0.95, legend_label="close")
    plot.add_tools(
        HoverTool(
            tooltips=[
                ("时间", "@open_time{%F %T}"),
                ("开盘", "@open{0,0.00}"),
                ("最高", "@high{0,0.00}"),
                ("最低", "@low{0,0.00}"),
                ("收盘", "@close{0,0.00}"),
                ("成交量", "@volume{0,0.####}"),
            ],
            formatters={"@open_time": "datetime"},
            mode="vline",
            renderers=[price_renderer],
        )
    )
    if trades:
        add_trade_markers(plot, trades, market_context)
    plot.legend.location = "top_left"
    plot.legend.click_policy = "hide"
    return plot


def add_trade_markers(plot, trades: list[TradeRecord], market_context: MarketContext) -> None:
    buy_rows = trade_marker_rows(trades, market_context, "buy")
    sell_rows = trade_marker_rows(trades, market_context, "sell")
    if buy_rows:
        buy_source = ColumnDataSource(pd.DataFrame(buy_rows))
        buy_renderer = plot.scatter("traded_at", "price", source=buy_source, marker="triangle", size=8, color="#4ade80", alpha=0.9, legend_label="buy")
        plot.add_tools(
            HoverTool(
                tooltips=[("成交时间", "@traded_at{%F %T}"), ("方向", "@side"), ("价格", "@price{0,0.00}"), ("数量", "@amount{0,0.####}")],
                formatters={"@traded_at": "datetime"},
                renderers=[buy_renderer],
            )
        )
    if sell_rows:
        sell_source = ColumnDataSource(pd.DataFrame(sell_rows))
        sell_renderer = plot.scatter("traded_at", "price", source=sell_source, marker="inverted_triangle", size=8, color="#fb7185", alpha=0.9, legend_label="sell")
        plot.add_tools(
            HoverTool(
                tooltips=[("成交时间", "@traded_at{%F %T}"), ("方向", "@side"), ("价格", "@price{0,0.00}"), ("数量", "@amount{0,0.####}")],
                formatters={"@traded_at": "datetime"},
                renderers=[sell_renderer],
            )
        )



def trade_marker_rows(trades: list[TradeRecord], market_context: MarketContext, side: str) -> list[dict[str, Any]]:
    return [
        {
            "traded_at": to_beijing_time(trade.traded_at),
            "side": trade.side,
            "price": float(trade.price),
            "amount": float(trade.amount),
        }
        for trade in trades
        if trade.symbol == market_context.symbol and trade.side == side
    ]



def base_time_series_figure(title: str, height: int):
    plot = figure(
        title=title,
        x_axis_type="datetime",
        height=height,
        sizing_mode="stretch_width",
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    plot.background_fill_color = "#101b2d"
    plot.border_fill_color = "#101b2d"
    plot.outline_line_color = "rgba(105, 181, 255, 0.18)"
    plot.title.text_color = "#eaf6ff"
    plot.title.text_font_size = "14px"
    plot.grid.grid_line_color = "#69b5ff"
    plot.grid.grid_line_alpha = 0.14
    plot.axis.axis_line_color = "#375a7a"
    plot.axis.major_tick_line_color = "#375a7a"
    plot.axis.minor_tick_line_color = "#375a7a"
    plot.axis.major_label_text_color = "#9db1c8"
    plot.legend.background_fill_color = "#101b2d"
    plot.legend.background_fill_alpha = 0.75
    plot.legend.border_line_color = "rgba(105, 181, 255, 0.18)"
    plot.legend.label_text_color = "#c8edff"
    plot.toolbar.logo = None
    return plot


def calculate_backtest_metrics(run: StrategyRun, data: DashboardData) -> dict[str, Any]:
    equity_df = records_to_dataframe(data.equity_curve)
    initial_equity = data.equity_curve[0].equity if data.equity_curve else run.initial_cash
    final_equity = data.equity_curve[-1].equity if data.equity_curve else run.final_equity
    total_return = final_equity / initial_equity - Decimal("1") if initial_equity and final_equity else None
    max_drawdown = None
    sharpe = None
    if not equity_df.empty and "equity" in equity_df.columns:
        equity = equity_df["equity"].astype(float)
        drawdowns = calculate_drawdown_series(equity)
        if not drawdowns.empty:
            max_drawdown = Decimal(str(drawdowns.min()))
        returns = equity.pct_change().dropna()
        if len(returns) > 1 and returns.std() != 0:
            sharpe = math.sqrt(365 * 24 * 12) * returns.mean() / returns.std()
    win_rate = calculate_backtest_win_rate(data.trades)
    return {
        "initial_equity": initial_equity,
        "final_equity": final_equity,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "sharpe": sharpe,
    }



def calculate_backtest_win_rate(trades: list[TradeRecord]) -> Decimal | None:
    realized_pnls = list(realized_pnls_by_trade_id(trades).values())
    if not realized_pnls:
        return None
    wins = [pnl for pnl in realized_pnls if pnl > 0]
    return Decimal(len(wins)) / Decimal(len(realized_pnls))



def calculate_backtest_trade_stats(trades: list[TradeRecord]) -> dict[str, Any]:
    realized_pnls = list(realized_pnls_by_trade_id(trades).values())
    wins = [pnl for pnl in realized_pnls if pnl > 0]
    losses = [pnl for pnl in realized_pnls if pnl < 0]
    total_win = sum(wins, Decimal("0"))
    total_loss = sum(losses, Decimal("0"))
    profit_factor = float(total_win / abs(total_loss)) if total_loss != 0 else None
    return {
        "win_count": len(wins),
        "loss_count": len(losses),
        "avg_win": total_win / len(wins) if wins else None,
        "avg_loss": total_loss / len(losses) if losses else None,
        "max_win": max(wins) if wins else None,
        "max_loss": min(losses) if losses else None,
        "total_fee": sum((Decimal(trade.fee or 0) for trade in trades), Decimal("0")),
        "profit_factor": profit_factor,
    }



def realized_pnls_by_trade_id(trades: list[TradeRecord]) -> dict[int, Decimal]:
    persisted_pnls = {trade.id: trade.realized_pnl for trade in trades if trade.realized_pnl is not None}
    if persisted_pnls:
        return persisted_pnls
    return calculate_realized_pnls_by_trade_id(trades)



def calculate_realized_pnls_by_trade_id(trades: list[TradeRecord]) -> dict[int, Decimal]:
    amount = Decimal("0")
    entry_price = Decimal("0")
    entry_fee = Decimal("0")
    realized_pnls: dict[int, Decimal] = {}
    for trade in sorted(trades, key=lambda item: item.traded_at):
        trade_amount = Decimal(trade.amount)
        trade_price = Decimal(trade.price)
        trade_fee = Decimal(trade.fee or 0)
        signed_amount = trade_amount if trade.side == "buy" else -trade_amount
        if amount == 0 or (amount > 0) == (signed_amount > 0):
            total_amount = abs(amount) + abs(signed_amount)
            entry_price = (entry_price * abs(amount) + trade_price * abs(signed_amount)) / total_amount
            entry_fee += trade_fee
            amount += signed_amount
            continue
        close_amount = min(abs(amount), abs(signed_amount))
        fee_share = entry_fee * close_amount / abs(amount)
        if amount > 0:
            pnl = (trade_price - entry_price) * close_amount - fee_share - trade_fee
        else:
            pnl = (entry_price - trade_price) * close_amount - fee_share - trade_fee
        realized_pnls[trade.id] = pnl
        remaining_amount = abs(amount) - close_amount
        if remaining_amount == 0:
            amount = Decimal("0")
            entry_price = Decimal("0")
            entry_fee = Decimal("0")
        else:
            amount += signed_amount
            entry_fee -= fee_share
    return realized_pnls



def build_backtest_fund_dataframe(chart_df: pd.DataFrame, initial_equity: Decimal | None) -> pd.DataFrame:
    fund_df = chart_df.copy()
    if "equity" not in fund_df.columns:
        return fund_df
    baseline = float(initial_equity) if initial_equity is not None else float(fund_df["equity"].iloc[0])
    fund_df["net_pnl"] = fund_df["equity"] - baseline
    fund_df["drawdown_amount"] = fund_df["equity"] - fund_df["equity"].cummax()
    return fund_df



def calculate_snapshot_status(latest_account: AccountSnapshot | None) -> dict[str, Any]:
    if latest_account is None or latest_account.timestamp is None:
        return {"timestamp": None, "age_seconds": None, "status": "无快照"}
    age_seconds = max(0, int((datetime.utcnow() - latest_account.timestamp).total_seconds()))
    if age_seconds <= 180:
        status = "正常"
    elif age_seconds <= 900:
        status = "延迟"
    else:
        status = "疑似停止"
    return {"timestamp": latest_account.timestamp, "age_seconds": age_seconds, "status": status}



def calculate_live_metrics(run: StrategyRun, data: DashboardData) -> dict[str, Any]:
    account_df = records_to_dataframe(data.account_snapshots)
    trade_pnls = [trade.realized_pnl for trade in data.trades if trade.realized_pnl is not None]
    winning_trades = [pnl for pnl in trade_pnls if pnl > 0]
    win_rate = Decimal(len(winning_trades)) / Decimal(len(trade_pnls)) if trade_pnls else None
    max_drawdown = None
    sharpe = None
    if not account_df.empty and "equity" in account_df.columns:
        equity = account_df["equity"].astype(float)
        drawdowns = calculate_drawdown_series(equity)
        if not drawdowns.empty:
            max_drawdown = Decimal(str(drawdowns.min()))
        returns = equity.pct_change().dropna()
        if len(returns) > 1 and returns.std() != 0:
            sharpe = math.sqrt(365 * 24 * 60) * returns.mean() / returns.std()
    return {
        "initial_cash": run.initial_cash,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "sharpe": sharpe,
        "trade_count": len(data.trades),
    }


def calculate_drawdown_series(equity: pd.Series) -> pd.Series:
    rolling_max = equity.cummax()
    return equity / rolling_max - 1


def format_decimal(value: Any) -> str:
    if value is None:
        return "-"
    return f"{Decimal(value):,.2f}"


def format_percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value * Decimal('100'):.4f}%"


def format_float(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"



def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return to_beijing_time(value).strftime("%Y-%m-%d %H:%M:%S")



def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60} 秒"
    hours = seconds // 3600
    minutes = seconds % 3600 // 60
    return f"{hours} 小时 {minutes} 分"


if __name__ == "__main__":
    main()