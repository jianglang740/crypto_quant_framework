import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from getpass import getpass

from crypto_quant.config import ExchangeConfig, MySQLConfig
from crypto_quant.database import LiveDatabaseRecorder, TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.database.models import TradeRecord
from crypto_quant.enums import OrderSide, OrderType, PositionSide, TradingMode
from crypto_quant.exchange import ExchangeClient
from crypto_quant.strategy.base import Account, Position, StrategyBase


SYMBOL = "BTC/USDT"
BASE_ASSET = "BTC"
QUOTE_ASSET = "USDT"
BUY_NOTIONAL_USDT = Decimal("20")


class TestnetPositionAndTradeStrategy(StrategyBase):
    name = "testnet_position_and_trade"


mysql_config = MySQLConfig(
    host="127.0.0.1",
    port=3306,
    username="crypto_quant_user",
    password=getpass("请输入本地 MySQL 密码："),
    database="crypto_quant",
)

okx_config = ExchangeConfig(
    api_key=os.environ["OKX_DEMO_API_KEY"],
    secret=os.environ["OKX_DEMO_SECRET_KEY"],
    password=os.environ["OKX_DEMO_PASSPHRASE"],
    trading_mode=TradingMode.SPOT,
    sandbox=True,
)


def decimal_from_balance(balance: dict, group: str, asset: str) -> Decimal:
    return Decimal(str(balance.get(group, {}).get(asset, 0)))


def decimal_from_value(value) -> Decimal:
    return Decimal(str(value or "0"))


def datetime_from_milliseconds(value) -> datetime:
    if value is None:
        return datetime.utcnow()
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)


def trade_record_from_ccxt(trade: dict, run_id: str, strategy_name: str) -> TradeRecord:
    fee = trade.get("fee") or {}
    return TradeRecord(
        run_id=run_id,
        strategy_name=strategy_name,
        exchange="okx_demo",
        exchange_trade_id=str(trade.get("id")) if trade.get("id") is not None else None,
        exchange_order_id=str(trade.get("order")) if trade.get("order") is not None else None,
        trading_mode=TradingMode.SPOT.value,
        symbol=trade["symbol"],
        side=trade["side"],
        position_side=PositionSide.BOTH.value,
        amount=decimal_from_value(trade.get("amount")),
        price=decimal_from_value(trade.get("price")),
        fee=decimal_from_value(fee.get("cost")),
        fee_asset=fee.get("currency"),
        traded_at=datetime_from_milliseconds(trade.get("timestamp")),
        raw=json.dumps(trade, ensure_ascii=False, default=str),
    )


def main() -> None:
    client = ExchangeClient(okx_config)
    client.load_markets()
    ticker = client.exchange.fetch_ticker(SYMBOL)
    last_price = Decimal(str(ticker["last"] or ticker["close"]))
    buy_amount = BUY_NOTIONAL_USDT / last_price

    mysql_engine = create_mysql_engine(mysql_config)
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)

    buy_order = None
    sell_order = None

    with Session() as session:
        repository = TradingRepository(session)
        strategy = TestnetPositionAndTradeStrategy(trading_mode=TradingMode.SPOT)
        recorder = LiveDatabaseRecorder(
            repository,
            run_name="okx_demo_position_and_trade",
        )
        run = recorder.start_run(
            strategy,
            symbols=[SYMBOL],
            config={
                "source": "examples/run_testnet_position_and_trade_recorder.py",
                "exchange": "okx_demo",
                "symbol": SYMBOL,
                "sandbox": True,
                "buy_notional_usdt": BUY_NOTIONAL_USDT,
            },
        )

        try:
            buy_order = client.create_order(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=float(buy_amount),
            )
            repository.save_order(
                buy_order,
                trading_mode=TradingMode.SPOT.value,
                run_id=run.run_id,
                strategy_name=strategy.name,
            )

            balance_after_buy = client.fetch_balance()
            btc_free = decimal_from_balance(balance_after_buy, "free", BASE_ASSET)
            usdt_free = decimal_from_balance(balance_after_buy, "free", QUOTE_ASSET)
            usdt_total = decimal_from_balance(balance_after_buy, "total", QUOTE_ASSET)

            strategy.account = Account(cash=usdt_total, equity=usdt_total, available=usdt_free)
            strategy.positions = {
                f"{SYMBOL}:{PositionSide.BOTH.value}": Position(
                    symbol=SYMBOL,
                    side=PositionSide.BOTH,
                    amount=btc_free,
                    entry_price=decimal_from_value(buy_order.get("average")) or last_price,
                    mark_price=last_price,
                )
            }
            recorder.record_snapshot(strategy)

            buy_trades = client.fetch_order_trades(str(buy_order["id"]), SYMBOL)
            for trade in buy_trades:
                repository.save_trade(trade_record_from_ccxt(trade, run.run_id, strategy.name))

            sell_amount = decimal_from_value(buy_order.get("filled")) or btc_free
            sell_order = client.create_order(
                symbol=SYMBOL,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=float(sell_amount),
            )
            repository.save_order(
                sell_order,
                trading_mode=TradingMode.SPOT.value,
                run_id=run.run_id,
                strategy_name=strategy.name,
            )

            sell_trades = client.fetch_order_trades(str(sell_order["id"]), SYMBOL)
            for trade in sell_trades:
                repository.save_trade(trade_record_from_ccxt(trade, run.run_id, strategy.name))

            finished_run = recorder.finish_run(strategy)
            positions = repository.get_position_snapshots(run.run_id)
            trades = repository.get_trades(run.run_id)
            orders = repository.get_orders(run.run_id)
        except Exception:
            if buy_order is not None and sell_order is None:
                try:
                    filled = decimal_from_value(buy_order.get("filled"))
                    if filled > 0:
                        client.create_order(
                            symbol=SYMBOL,
                            side=OrderSide.SELL,
                            order_type=OrderType.MARKET,
                            amount=float(filled),
                        )
                except Exception:
                    pass
            repository.finish_run(run.run_id, status="failed")
            raise

    print("OKX Demo 持仓和成交入库完成")
    print(f"symbol: {SYMBOL}")
    print(f"last_price: {last_price}")
    print(f"buy_amount: {buy_amount}")
    print(f"buy_order_id: {buy_order.get('id') if buy_order else None}")
    print(f"buy_status: {buy_order.get('status') if buy_order else None}")
    print(f"buy_filled: {buy_order.get('filled') if buy_order else None}")
    print(f"sell_order_id: {sell_order.get('id') if sell_order else None}")
    print(f"sell_status: {sell_order.get('status') if sell_order else None}")
    print(f"sell_filled: {sell_order.get('filled') if sell_order else None}")
    print(f"run_id: {finished_run.run_id}")
    print(f"status: {finished_run.status}")
    print(f"orders: {len(orders)}")
    print(f"position_snapshots: {len(positions)}")
    print(f"trades: {len(trades)}")


if __name__ == "__main__":
    main()
