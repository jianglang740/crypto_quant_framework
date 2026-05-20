import json
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from crypto_quant.data.feed import BarData
from crypto_quant.database.models import EquityCurve, Kline, OrderRecord, TradeRecord


class MarketDataRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_klines(self, bars: list[BarData]) -> None:
        for bar in bars:
            statement = insert(Kline).values(
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                open_time=bar.datetime.replace(tzinfo=None),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            update_columns = {
                "open": statement.inserted.open,
                "high": statement.inserted.high,
                "low": statement.inserted.low,
                "close": statement.inserted.close,
                "volume": statement.inserted.volume,
            }
            self.session.execute(statement.on_duplicate_key_update(**update_columns))
        self.session.commit()


class TradingRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_order(self, order: dict[str, Any], trading_mode: str) -> OrderRecord:
        record = OrderRecord(
            exchange_order_id=str(order.get("id")) if order.get("id") is not None else None,
            symbol=order["symbol"],
            trading_mode=trading_mode,
            side=order["side"],
            order_type=order["type"],
            status=order.get("status", "open"),
            amount=Decimal(str(order.get("amount") or "0")),
            price=Decimal(str(order["price"])) if order.get("price") is not None else None,
            filled=Decimal(str(order.get("filled") or "0")),
            average=Decimal(str(order["average"])) if order.get("average") is not None else None,
            raw=json.dumps(order, ensure_ascii=False, default=str),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_trade(self, trade: TradeRecord) -> TradeRecord:
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def save_equity(self, equity: EquityCurve) -> EquityCurve:
        self.session.add(equity)
        self.session.commit()
        self.session.refresh(equity)
        return equity
