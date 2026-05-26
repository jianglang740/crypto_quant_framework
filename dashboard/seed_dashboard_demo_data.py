from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete

from crypto_quant.config import MySQLConfig
from crypto_quant.database import create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.database.models import AccountSnapshot, EquityCurve, OrderRecord, PositionSnapshot, StrategyRun, TradeRecord


DEMO_RUN_PREFIX = "dashboard_demo_"


def main() -> None:
    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)
    with Session() as session:
        clear_existing_demo_data(session)
        create_backtest_demo(session)
        create_live_demo(session)
        session.commit()
    print("dashboard demo data inserted successfully")


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE", "crypto_quant"),
    )


def clear_existing_demo_data(session) -> None:
    demo_run_ids = list(
        session.scalars(
            StrategyRun.__table__.select()
            .with_only_columns(StrategyRun.run_id)
            .where(StrategyRun.run_id.like(f"{DEMO_RUN_PREFIX}%"))
        )
    )
    if not demo_run_ids:
        return
    for model in [OrderRecord, TradeRecord, EquityCurve, AccountSnapshot, PositionSnapshot]:
        session.execute(delete(model).where(model.run_id.in_(demo_run_ids)))
    session.execute(delete(StrategyRun).where(StrategyRun.run_id.in_(demo_run_ids)))


def create_backtest_demo(session) -> None:
    run_id = f"{DEMO_RUN_PREFIX}momentum_trend_backtest"
    strategy_name = "dashboard_momentum_trend_futures"
    start = datetime(2026, 5, 1, 0, 0, 0)
    initial_cash = Decimal("10000")
    equity_points = build_equity_series(initial_cash, 96, Decimal("0.0018"), Decimal("0.006"))
    final_equity = equity_points[-1]

    session.add(
        StrategyRun(
            run_id=run_id,
            name="Dashboard Demo - Momentum Trend Backtest",
            run_type="backtest",
            trading_mode="future",
            strategy_name=strategy_name,
            symbols=json.dumps(["ETH/USDT"], ensure_ascii=False),
            timeframe="15m",
            started_at=start,
            ended_at=start + timedelta(minutes=15 * 95),
            initial_cash=initial_cash,
            final_equity=final_equity,
            status="finished",
            config=json.dumps(
                {
                    "source": "dashboard/seed_dashboard_demo_data.py",
                    "purpose": "dashboard chart demo",
                    "leverage": "2",
                    "commission_rate": "0.0004",
                },
                ensure_ascii=False,
            ),
        )
    )

    realized_pnl = Decimal("0")
    for index, equity in enumerate(equity_points):
        timestamp = start + timedelta(minutes=15 * index)
        unrealized = equity - initial_cash - realized_pnl
        session.add(
            EquityCurve(
                run_id=run_id,
                strategy_name=strategy_name,
                trading_mode="future",
                timestamp=timestamp,
                cash=initial_cash + realized_pnl,
                equity=equity,
                available=equity - Decimal("650"),
                margin=Decimal("650"),
                maintenance_margin=Decimal("65"),
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized,
            )
        )

    trade_specs = [
        (6, "buy", "long", Decimal("1.20"), Decimal("3040"), Decimal("0")),
        (18, "sell", "long", Decimal("1.20"), Decimal("3128"), Decimal("105.60")),
        (29, "sell", "short", Decimal("1.00"), Decimal("3185"), Decimal("0")),
        (43, "buy", "short", Decimal("1.00"), Decimal("3092"), Decimal("93.00")),
        (55, "buy", "long", Decimal("1.35"), Decimal("3060"), Decimal("0")),
        (72, "sell", "long", Decimal("1.35"), Decimal("3215"), Decimal("209.25")),
        (80, "sell", "short", Decimal("0.80"), Decimal("3230"), Decimal("0")),
        (92, "buy", "short", Decimal("0.80"), Decimal("3198"), Decimal("25.60")),
    ]
    create_orders_and_trades(session, run_id, strategy_name, "future", "ETH/USDT", start, trade_specs, 15)


def create_live_demo(session) -> None:
    run_id = f"{DEMO_RUN_PREFIX}dry_run_live_overview"
    strategy_name = "dashboard_live_observer"
    start = datetime(2026, 5, 24, 9, 0, 0)
    initial_cash = Decimal("10000")
    equity_points = build_equity_series(initial_cash, 36, Decimal("0.0009"), Decimal("0.0028"))
    final_equity = equity_points[-1]

    session.add(
        StrategyRun(
            run_id=run_id,
            name="Dashboard Demo - Dry Run Live Overview",
            run_type="dry_run",
            trading_mode="future",
            strategy_name=strategy_name,
            symbols=json.dumps(["BTC/USDT", "ETH/USDT"], ensure_ascii=False),
            timeframe="1m",
            started_at=start,
            ended_at=start + timedelta(minutes=35),
            initial_cash=initial_cash,
            final_equity=final_equity,
            status="finished",
            config=json.dumps(
                {
                    "source": "dashboard/seed_dashboard_demo_data.py",
                    "purpose": "live overview demo",
                    "dry_run": True,
                },
                ensure_ascii=False,
            ),
        )
    )

    realized_pnl = Decimal("38.50")
    for index, equity in enumerate(equity_points):
        timestamp = start + timedelta(minutes=index)
        margin = Decimal("420") + Decimal(index % 5) * Decimal("8")
        maintenance = margin * Decimal("0.10")
        unrealized = equity - initial_cash - realized_pnl
        session.add(
            AccountSnapshot(
                run_id=run_id,
                timestamp=timestamp,
                trading_mode="future",
                cash=initial_cash + realized_pnl,
                equity=equity,
                available=equity - margin,
                margin=margin,
                maintenance_margin=maintenance,
                margin_ratio=maintenance / equity,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized,
                raw=json.dumps({"demo": True, "index": index}, ensure_ascii=False),
            )
        )
        session.add(
            PositionSnapshot(
                run_id=run_id,
                strategy_name=strategy_name,
                timestamp=timestamp,
                symbol="BTC/USDT",
                side="long",
                amount=Decimal("0.018"),
                entry_price=Decimal("68400"),
                mark_price=Decimal("68400") + Decimal(index * 9),
                margin=Decimal("240"),
                liquidation_price=Decimal("51800"),
                unrealized_pnl=Decimal(index) * Decimal("0.162"),
                raw=json.dumps({"demo": True}, ensure_ascii=False),
            )
        )
        session.add(
            PositionSnapshot(
                run_id=run_id,
                strategy_name=strategy_name,
                timestamp=timestamp,
                symbol="ETH/USDT",
                side="short",
                amount=Decimal("0.55"),
                entry_price=Decimal("3180"),
                mark_price=Decimal("3180") - Decimal(index * 1.7),
                margin=Decimal("180"),
                liquidation_price=Decimal("4160"),
                unrealized_pnl=Decimal(index) * Decimal("0.935"),
                raw=json.dumps({"demo": True}, ensure_ascii=False),
            )
        )

    trade_specs = [
        (2, "buy", "long", Decimal("0.018"), Decimal("68400"), Decimal("0")),
        (8, "sell", "short", Decimal("0.55"), Decimal("3180"), Decimal("0")),
        (19, "buy", "short", Decimal("0.20"), Decimal("3158"), Decimal("4.40")),
        (28, "sell", "long", Decimal("0.006"), Decimal("68760"), Decimal("2.16")),
    ]
    create_orders_and_trades(session, run_id, strategy_name, "future", "BTC/USDT", start, trade_specs[:1] + trade_specs[3:], 1)
    create_orders_and_trades(session, run_id, strategy_name, "future", "ETH/USDT", start, trade_specs[1:3], 1)


def build_equity_series(initial: Decimal, count: int, drift: Decimal, wave: Decimal) -> list[Decimal]:
    values: list[Decimal] = []
    equity = initial
    for index in range(count):
        cycle = Decimal((index % 12) - 5) * wave
        pullback = Decimal("-0.018") if index in {22, 23, 24, 58, 59} else Decimal("0")
        recovery = Decimal("0.012") if index in {25, 60, 61} else Decimal("0")
        step = drift + cycle + pullback + recovery
        equity = max(Decimal("1000"), equity * (Decimal("1") + step))
        values.append(equity.quantize(Decimal("0.000001")))
    return values


def create_orders_and_trades(
    session,
    run_id: str,
    strategy_name: str,
    trading_mode: str,
    symbol: str,
    start: datetime,
    trade_specs: list[tuple[int, str, str, Decimal, Decimal, Decimal]],
    minute_step: int,
) -> None:
    for index, (bar_index, side, position_side, amount, price, realized_pnl) in enumerate(trade_specs, start=1):
        timestamp = start + timedelta(minutes=minute_step * bar_index)
        fee = (amount * price * Decimal("0.0004")).quantize(Decimal("0.000001"))
        client_order_id = f"{run_id}_order_{symbol.replace('/', '').lower()}_{index}"
        exchange_order_id = f"demo_ex_{client_order_id}"
        session.add(
            OrderRecord(
                run_id=run_id,
                strategy_name=strategy_name,
                exchange="binance",
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                symbol=symbol,
                trading_mode=trading_mode,
                side=side,
                order_type="market",
                status="closed",
                amount=amount,
                price=None,
                filled=amount,
                average=price,
                position_side=position_side,
                reduce_only=realized_pnl != Decimal("0"),
                time_in_force=None,
                raw=json.dumps({"demo": True, "source": "dashboard seed"}, ensure_ascii=False),
                created_at=timestamp,
                updated_at=timestamp + timedelta(seconds=2),
            )
        )
        session.add(
            TradeRecord(
                run_id=run_id,
                strategy_name=strategy_name,
                exchange="binance",
                exchange_trade_id=f"demo_trade_{client_order_id}",
                exchange_order_id=exchange_order_id,
                trading_mode=trading_mode,
                symbol=symbol,
                side=side,
                position_side=position_side,
                amount=amount,
                price=price,
                fee=fee,
                fee_asset="USDT",
                realized_pnl=realized_pnl - fee if realized_pnl != Decimal("0") else None,
                traded_at=timestamp + timedelta(seconds=1),
                raw=json.dumps({"demo": True, "source": "dashboard seed"}, ensure_ascii=False),
                created_at=timestamp + timedelta(seconds=1),
            )
        )


if __name__ == "__main__":
    main()
