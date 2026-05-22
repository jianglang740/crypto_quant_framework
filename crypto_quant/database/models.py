from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    run_type: Mapped[str] = mapped_column(String(32))
    trading_mode: Mapped[str] = mapped_column(String(16))
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbols: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    initial_cash: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    final_equity: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Kline(Base):
    __tablename__ = "klines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(32), default="binance")
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(16))
    open_time: Mapped[datetime] = mapped_column(DateTime)
    open: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    high: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    low: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    close: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    volume: Mapped[Decimal] = mapped_column(Numeric(36, 18))

    __table_args__ = (Index("uq_klines_exchange_symbol_tf_time", "exchange", "symbol", "timeframe", "open_time", unique=True),)


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange: Mapped[str] = mapped_column(String(32), default="binance")
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32))
    trading_mode: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(16))
    order_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    price: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    filled: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    average: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    position_side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    time_in_force: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_orders_run_strategy", "run_id", "strategy_name"),)


class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange: Mapped[str] = mapped_column(String(32), default="binance")
    exchange_trade_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trading_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(16))
    position_side: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    price: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    fee: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    fee_asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    traded_at: Mapped[datetime] = mapped_column(DateTime)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_trades_run_strategy", "run_id", "strategy_name"),)


class EquityCurve(Base):
    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(128))
    trading_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    cash: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    equity: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    available: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    margin: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    maintenance_margin: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)

    __table_args__ = (Index("ix_equity_curve_run_time", "run_id", "timestamp"),)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    trading_mode: Mapped[str] = mapped_column(String(16))
    cash: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    equity: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    available: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    margin: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    maintenance_margin: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    margin_ratio: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_account_snapshots_run_time", "run_id", "timestamp"),)


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64))
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    mark_price: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    margin: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    liquidation_price: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_position_snapshots_run_time", "run_id", "timestamp"),)
