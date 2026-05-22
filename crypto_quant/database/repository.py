import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.database.models import (
    AccountSnapshot,
    EquityCurve,
    Kline,
    OrderRecord,
    PositionSnapshot,
    StrategyRun,
    TradeRecord,
)
from crypto_quant.strategy.base import Account, LocalOrder, Position, StrategyBase, Trade


class MarketDataRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_klines(self, bars: list[BarData], exchange: str = "binance") -> None:
        for bar in bars:
            statement = insert(Kline).values(
                exchange=exchange,
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

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        exchange: str = "binance",
        limit: int | None = None,
    ) -> list[Kline]:
        statement: Select[tuple[Kline]] = (
            select(Kline)
            .where(Kline.exchange == exchange)
            .where(Kline.symbol == symbol)
            .where(Kline.timeframe == timeframe)
            .order_by(Kline.open_time.asc())
        )
        if start is not None:
            statement = statement.where(Kline.open_time >= start.replace(tzinfo=None))
        if end is not None:
            statement = statement.where(Kline.open_time <= end.replace(tzinfo=None))
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement).all())

    def get_data_feed(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        exchange: str = "binance",
        limit: int | None = None,
    ) -> DataFeed:
        klines = self.get_klines(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            exchange=exchange,
            limit=limit,
        )
        return DataFeed(
            [
                BarData(
                    symbol=kline.symbol,
                    timeframe=kline.timeframe,
                    datetime=kline.open_time,
                    open=kline.open,
                    high=kline.high,
                    low=kline.low,
                    close=kline.close,
                    volume=kline.volume,
                )
                for kline in klines
            ]
        )


class TradingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run(
        self,
        name: str,
        run_type: str,
        trading_mode: str,
        strategy_name: str | None = None,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        initial_cash: Decimal | None = None,
        config: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> StrategyRun:
        run = StrategyRun(
            run_id=run_id or str(uuid4()),
            name=name,
            run_type=run_type,
            trading_mode=trading_mode,
            strategy_name=strategy_name,
            symbols=json.dumps(symbols, ensure_ascii=False) if symbols is not None else None,
            timeframe=timeframe,
            initial_cash=initial_cash,
            status="running",
            config=json.dumps(config, ensure_ascii=False, default=str) if config is not None else None,
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def finish_run(self, run_id: str, final_equity: Decimal | None = None, status: str = "finished") -> StrategyRun:
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"unknown run_id: {run_id}")
        run.ended_at = datetime.utcnow()
        run.final_equity = final_equity
        run.status = status
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run(self, run_id: str) -> StrategyRun | None:
        return self.session.scalar(select(StrategyRun).where(StrategyRun.run_id == run_id))

    def list_runs(
        self,
        run_type: str | None = None,
        strategy_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[StrategyRun]:
        statement: Select[tuple[StrategyRun]] = select(StrategyRun).order_by(StrategyRun.created_at.desc())
        if run_type is not None:
            statement = statement.where(StrategyRun.run_type == run_type)
        if strategy_name is not None:
            statement = statement.where(StrategyRun.strategy_name == strategy_name)
        if status is not None:
            statement = statement.where(StrategyRun.status == status)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement).all())

    def get_orders(
        self,
        run_id: str,
        strategy_name: str | None = None,
        status: str | None = None,
    ) -> list[OrderRecord]:
        statement: Select[tuple[OrderRecord]] = select(OrderRecord).where(OrderRecord.run_id == run_id).order_by(OrderRecord.created_at.asc())
        if strategy_name is not None:
            statement = statement.where(OrderRecord.strategy_name == strategy_name)
        if status is not None:
            statement = statement.where(OrderRecord.status == status)
        return list(self.session.scalars(statement).all())

    def get_trades(self, run_id: str, strategy_name: str | None = None) -> list[TradeRecord]:
        statement: Select[tuple[TradeRecord]] = select(TradeRecord).where(TradeRecord.run_id == run_id).order_by(TradeRecord.traded_at.asc())
        if strategy_name is not None:
            statement = statement.where(TradeRecord.strategy_name == strategy_name)
        return list(self.session.scalars(statement).all())

    def get_equity_curve(self, run_id: str, strategy_name: str | None = None) -> list[EquityCurve]:
        statement: Select[tuple[EquityCurve]] = select(EquityCurve).where(EquityCurve.run_id == run_id).order_by(EquityCurve.timestamp.asc())
        if strategy_name is not None:
            statement = statement.where(EquityCurve.strategy_name == strategy_name)
        return list(self.session.scalars(statement).all())

    def get_account_snapshots(self, run_id: str) -> list[AccountSnapshot]:
        statement: Select[tuple[AccountSnapshot]] = select(AccountSnapshot).where(AccountSnapshot.run_id == run_id).order_by(AccountSnapshot.timestamp.asc())
        return list(self.session.scalars(statement).all())

    def get_position_snapshots(
        self,
        run_id: str,
        strategy_name: str | None = None,
        symbol: str | None = None,
    ) -> list[PositionSnapshot]:
        statement: Select[tuple[PositionSnapshot]] = select(PositionSnapshot).where(PositionSnapshot.run_id == run_id).order_by(PositionSnapshot.timestamp.asc())
        if strategy_name is not None:
            statement = statement.where(PositionSnapshot.strategy_name == strategy_name)
        if symbol is not None:
            statement = statement.where(PositionSnapshot.symbol == symbol)
        return list(self.session.scalars(statement).all())

    def save_order(self, order: dict[str, Any], trading_mode: str, run_id: str | None = None, strategy_name: str | None = None) -> OrderRecord:
        record = OrderRecord(
            run_id=run_id,
            strategy_name=strategy_name,
            exchange_order_id=str(order.get("id")) if order.get("id") is not None else None,
            client_order_id=str(order.get("clientOrderId")) if order.get("clientOrderId") is not None else None,
            symbol=order["symbol"],
            trading_mode=trading_mode,
            side=order["side"],
            order_type=order["type"],
            status=order.get("status", "open"),
            amount=Decimal(str(order.get("amount") or "0")),
            price=Decimal(str(order["price"])) if order.get("price") is not None else None,
            filled=Decimal(str(order.get("filled") or "0")),
            average=Decimal(str(order["average"])) if order.get("average") is not None else None,
            position_side=(order.get("info") or {}).get("positionSide"),
            reduce_only=bool(order.get("reduceOnly") or (order.get("info") or {}).get("reduceOnly") or False),
            time_in_force=order.get("timeInForce") or (order.get("info") or {}).get("timeInForce"),
            raw=json.dumps(order, ensure_ascii=False, default=str),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_local_order(
        self,
        order: LocalOrder,
        trading_mode: str,
        run_id: str | None = None,
        strategy_name: str | None = None,
        exchange: str = "binance",
    ) -> OrderRecord:
        request = order.request
        record = OrderRecord(
            run_id=run_id,
            strategy_name=strategy_name,
            exchange=exchange,
            client_order_id=order.id,
            symbol=request.symbol,
            trading_mode=trading_mode,
            side=request.side.value,
            order_type=request.order_type.value,
            status=order.status.value,
            amount=request.amount,
            price=request.price,
            filled=order.filled,
            average=order.average,
            position_side=request.position_side.value if request.position_side is not None else None,
            reduce_only=request.reduce_only,
            time_in_force=request.time_in_force.value if request.time_in_force is not None else None,
            raw=self._local_order_raw(order),
            created_at=order.created_at.replace(tzinfo=None),
            updated_at=datetime.utcnow(),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def upsert_local_order(
        self,
        order: LocalOrder,
        trading_mode: str,
        run_id: str | None = None,
        strategy_name: str | None = None,
        exchange: str = "binance",
    ) -> OrderRecord:
        statement: Select[tuple[OrderRecord]] = select(OrderRecord).where(OrderRecord.client_order_id == order.id)
        if run_id is not None:
            statement = statement.where(OrderRecord.run_id == run_id)
        record = self.session.scalar(statement)
        if record is None:
            return self.save_local_order(order, trading_mode=trading_mode, run_id=run_id, strategy_name=strategy_name, exchange=exchange)
        request = order.request
        record.strategy_name = strategy_name
        record.exchange = exchange
        record.symbol = request.symbol
        record.trading_mode = trading_mode
        record.side = request.side.value
        record.order_type = request.order_type.value
        record.status = order.status.value
        record.amount = request.amount
        record.price = request.price
        record.filled = order.filled
        record.average = order.average
        record.position_side = request.position_side.value if request.position_side is not None else None
        record.reduce_only = request.reduce_only
        record.time_in_force = request.time_in_force.value if request.time_in_force is not None else None
        record.raw = self._local_order_raw(order)
        record.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_order_status(
        self,
        order_id: str,
        status: str,
        run_id: str | None = None,
        filled: Decimal | None = None,
        average: Decimal | None = None,
    ) -> OrderRecord:
        statement: Select[tuple[OrderRecord]] = select(OrderRecord).where(
            (OrderRecord.client_order_id == order_id) | (OrderRecord.exchange_order_id == order_id)
        )
        if run_id is not None:
            statement = statement.where(OrderRecord.run_id == run_id)
        record = self.session.scalar(statement)
        if record is None:
            raise ValueError(f"unknown order_id: {order_id}")
        record.status = status
        if filled is not None:
            record.filled = filled
        if average is not None:
            record.average = average
        record.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_trade(self, trade: TradeRecord) -> TradeRecord:
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def save_framework_trade(
        self,
        trade: Trade,
        trading_mode: str | None = None,
        run_id: str | None = None,
        strategy_name: str | None = None,
        exchange_order_id: str | None = None,
        position_side: str | None = None,
        exchange: str = "binance",
    ) -> TradeRecord:
        record = TradeRecord(
            run_id=run_id,
            strategy_name=strategy_name,
            exchange=exchange,
            exchange_trade_id=trade.id,
            exchange_order_id=exchange_order_id,
            trading_mode=trading_mode,
            symbol=trade.symbol,
            side=trade.side.value,
            position_side=position_side,
            amount=trade.amount,
            price=trade.price,
            fee=trade.fee,
            traded_at=trade.traded_at.replace(tzinfo=None),
            raw=json.dumps(self._trade_to_dict(trade), ensure_ascii=False, default=str),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_equity(self, equity: EquityCurve) -> EquityCurve:
        self.session.add(equity)
        self.session.commit()
        self.session.refresh(equity)
        return equity

    def save_equity_point(
        self,
        timestamp: datetime,
        account: Account,
        strategy_name: str,
        run_id: str | None = None,
        trading_mode: str | None = None,
    ) -> EquityCurve:
        record = EquityCurve(
            run_id=run_id,
            strategy_name=strategy_name,
            trading_mode=trading_mode,
            timestamp=timestamp.replace(tzinfo=None),
            cash=account.cash,
            equity=account.equity,
            available=account.available,
            margin=account.margin,
            maintenance_margin=account.maintenance_margin,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_account_snapshot(
        self,
        account: Account,
        run_id: str,
        trading_mode: str,
        timestamp: datetime | None = None,
        raw: dict[str, Any] | None = None,
    ) -> AccountSnapshot:
        record = AccountSnapshot(
            run_id=run_id,
            timestamp=(timestamp or datetime.utcnow()).replace(tzinfo=None),
            trading_mode=trading_mode,
            cash=account.cash,
            equity=account.equity,
            available=account.available,
            margin=account.margin,
            maintenance_margin=account.maintenance_margin,
            margin_ratio=account.margin_ratio,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
            raw=json.dumps(raw, ensure_ascii=False, default=str) if raw is not None else None,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_position_snapshot(
        self,
        position: Position,
        run_id: str,
        timestamp: datetime | None = None,
        strategy_name: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> PositionSnapshot:
        record = PositionSnapshot(
            run_id=run_id,
            strategy_name=strategy_name,
            timestamp=(timestamp or datetime.utcnow()).replace(tzinfo=None),
            symbol=position.symbol,
            side=position.side.value,
            amount=position.amount,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            margin=position.margin,
            liquidation_price=position.liquidation_price,
            unrealized_pnl=position.unrealized_pnl,
            raw=json.dumps(raw, ensure_ascii=False, default=str) if raw is not None else None,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_live_snapshot(self, strategy: StrategyBase, run_id: str, timestamp: datetime | None = None) -> None:
        snapshot_time = timestamp or datetime.utcnow()
        self.save_account_snapshot(
            account=strategy.account,
            run_id=run_id,
            trading_mode=strategy.trading_mode.value,
            timestamp=snapshot_time,
        )
        for position in strategy.positions.values():
            if not position.is_flat:
                self.save_position_snapshot(position, run_id=run_id, timestamp=snapshot_time, strategy_name=strategy.name)
        for order in strategy.orders.values():
            self.upsert_local_order(order, trading_mode=strategy.trading_mode.value, run_id=run_id, strategy_name=strategy.name)

    def save_backtest_result(
        self,
        result: Any,
        strategy_name: str,
        trading_mode: str,
        run_id: str | None = None,
        run_name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> StrategyRun:
        run = self.create_run(
            name=run_name or strategy_name,
            run_type="portfolio_backtest" if hasattr(result, "strategy_trades") else "backtest",
            trading_mode=trading_mode,
            strategy_name=strategy_name,
            initial_cash=result.equity_curve[0][1] if result.equity_curve else None,
            config=config,
            run_id=run_id,
        )
        actual_run_id = run.run_id
        self._save_result_orders(result, trading_mode, actual_run_id, strategy_name)
        self._save_result_trades(result, trading_mode, actual_run_id, strategy_name)
        for timestamp, equity in result.equity_curve:
            account = Account(
                cash=result.final_account.cash,
                equity=equity,
                available=result.final_account.available,
                margin=result.final_account.margin,
                maintenance_margin=result.final_account.maintenance_margin,
                margin_ratio=result.final_account.margin_ratio,
                realized_pnl=result.final_account.realized_pnl,
                unrealized_pnl=result.final_account.unrealized_pnl,
            )
            self.save_equity_point(
                timestamp=timestamp,
                account=account,
                strategy_name=strategy_name,
                run_id=actual_run_id,
                trading_mode=trading_mode,
            )
        return self.finish_run(actual_run_id, final_equity=result.final_account.equity)

    def _save_result_orders(self, result: Any, trading_mode: str, run_id: str, default_strategy_name: str) -> None:
        if hasattr(result, "strategy_orders") and result.strategy_orders:
            for strategy_name, orders in result.strategy_orders.items():
                for order in orders:
                    self.save_local_order(order, trading_mode=trading_mode, run_id=run_id, strategy_name=strategy_name)
            return
        for order in getattr(result, "orders", []):
            self.save_local_order(order, trading_mode=trading_mode, run_id=run_id, strategy_name=default_strategy_name)

    def _save_result_trades(self, result: Any, trading_mode: str, run_id: str, default_strategy_name: str) -> None:
        if hasattr(result, "strategy_trades") and result.strategy_trades:
            for strategy_name, trades in result.strategy_trades.items():
                for trade in trades:
                    self.save_framework_trade(trade, trading_mode=trading_mode, run_id=run_id, strategy_name=strategy_name)
            return
        for trade in getattr(result, "trades", []):
            self.save_framework_trade(trade, trading_mode=trading_mode, run_id=run_id, strategy_name=default_strategy_name)

    def _local_order_raw(self, order: LocalOrder) -> str:
        request = order.request
        return json.dumps(
            {
                "id": order.id,
                "symbol": request.symbol,
                "side": request.side.value,
                "type": request.order_type.value,
                "amount": request.amount,
                "price": request.price,
                "position_side": request.position_side.value if request.position_side is not None else None,
                "reduce_only": request.reduce_only,
                "time_in_force": request.time_in_force.value if request.time_in_force is not None else None,
                "params": request.params,
                "status": order.status.value,
                "filled": order.filled,
                "average": order.average,
                "created_at": order.created_at,
            },
            ensure_ascii=False,
            default=str,
        )

    def _trade_to_dict(self, trade: Trade) -> dict[str, Any]:
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side.value,
            "amount": trade.amount,
            "price": trade.price,
            "fee": trade.fee,
            "traded_at": trade.traded_at,
        }
