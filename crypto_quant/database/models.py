from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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

    __table_args__ = (Index("uq_klines_symbol_tf_time", "symbol", "timeframe", "open_time", unique=True),)


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32))
    trading_mode: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(16))
    order_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    price: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    filled: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    average: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TradeRecord(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    price: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    fee: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    traded_at: Mapped[datetime] = mapped_column(DateTime)


class EquityCurve(Base):
    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    cash: Mapped[Decimal] = mapped_column(Numeric(36, 18))
    equity: Mapped[Decimal] = mapped_column(Numeric(36, 18))
