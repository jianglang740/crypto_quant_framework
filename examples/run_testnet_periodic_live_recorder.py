import json
import os
import time
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
LIMIT_ORDER_NOTIONAL_USDT = Decimal("20")
MARKET_BUY_NOTIONAL_USDT = Decimal("20")
CYCLES = 5
POLL_SECONDS = 3


class TestnetPeriodicRecorderStrategy(StrategyBase):
    name = "testnet_periodic_live_recorder"


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


def trade_key(trade: dict) -> str:
    trade_id = trade.get("id")
    order_id = trade.get("order")
    if trade_id is not None:
        return f"trade:{trade_id}"
    return json.dumps(
        {
            "order": order_id,
            "timestamp": trade.get("timestamp"),
            "side": trade.get("side"),
            "amount": trade.get("amount"),
            "price": trade.get("price"),
        },
        sort_keys=True,
        default=str,
    )


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


def sync_account_and_position(
    strategy: StrategyBase,
    client: ExchangeClient,
    mark_price: Decimal,
    entry_price: Decimal,
) -> None:
    balance = client.fetch_balance()
    base_free = decimal_from_balance(balance, "free", BASE_ASSET)
    quote_free = decimal_from_balance(balance, "free", QUOTE_ASSET)
    quote_total = decimal_from_balance(balance, "total", QUOTE_ASSET)

    position_value = base_free * mark_price
    strategy.account = Account(
        cash=quote_total,
        equity=quote_total + position_value,
        available=quote_free,
    )

    if base_free > 0:
        strategy.positions = {
            f"{SYMBOL}:{PositionSide.BOTH.value}": Position(
                symbol=SYMBOL,
                side=PositionSide.BOTH,
                amount=base_free,
                entry_price=entry_price,
                mark_price=mark_price,
                unrealized_pnl=(mark_price - entry_price) * base_free,
            )
        }
    else:
        strategy.positions = {}


def save_order_once(
    repository: TradingRepository,
    seen_order_ids: set[str],
    order: dict,
    run_id: str,
    strategy_name: str,
) -> None:
    order_id = str(order.get("id") or order.get("clientOrderId"))
    if not order_id or order_id in seen_order_ids:
        return
    repository.save_order(
        order,
        trading_mode=TradingMode.SPOT.value,
        run_id=run_id,
        strategy_name=strategy_name,
    )
    seen_order_ids.add(order_id)


def update_order_from_exchange(
    repository: TradingRepository,
    order: dict,
    run_id: str,
) -> None:
    order_id = str(order.get("id") or order.get("clientOrderId"))
    repository.update_order_status(
        order_id,
        order.get("status", "open"),
        run_id=run_id,
        filled=decimal_from_value(order.get("filled")),
        average=Decimal(str(order["average"])) if order.get("average") is not None else None,
    )


def save_trades_once(
    repository: TradingRepository,
    seen_trade_ids: set[str],
    trades: list[dict],
    run_id: str,
    strategy_name: str,
) -> int:
    saved_count = 0
    for trade in trades:
        key = trade_key(trade)
        if key in seen_trade_ids:
            continue
        repository.save_trade(trade_record_from_ccxt(trade, run_id, strategy_name))
        seen_trade_ids.add(key)
        saved_count += 1
    return saved_count


def print_cycle(title: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {title}")


def main() -> None:
    client = ExchangeClient(okx_config)
    client.load_markets()
    ticker = client.exchange.fetch_ticker(SYMBOL)
    last_price = Decimal(str(ticker["last"] or ticker["close"]))
    limit_price = last_price * Decimal("0.8")
    limit_amount = LIMIT_ORDER_NOTIONAL_USDT / limit_price
    buy_amount = MARKET_BUY_NOTIONAL_USDT / last_price

    mysql_engine = create_mysql_engine(mysql_config)
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)

    limit_order = None
    limit_fetched_order = None
    limit_canceled_order = None
    buy_order = None
    sell_order = None
    finished_run = None
    seen_order_ids: set[str] = set()
    seen_trade_ids: set[str] = set()

    with Session() as session:
        repository = TradingRepository(session)
        strategy = TestnetPeriodicRecorderStrategy(trading_mode=TradingMode.SPOT)
        recorder = LiveDatabaseRecorder(
            repository,
            run_name="okx_demo_periodic_live_recorder",
        )
        run = recorder.start_run(
            strategy,
            symbols=[SYMBOL],
            config={
                "source": "examples/run_testnet_periodic_live_recorder.py",
                "exchange": "okx_demo",
                "symbol": SYMBOL,
                "sandbox": True,
                "cycles": CYCLES,
                "poll_seconds": POLL_SECONDS,
                "limit_order_notional_usdt": LIMIT_ORDER_NOTIONAL_USDT,
                "market_buy_notional_usdt": MARKET_BUY_NOTIONAL_USDT,
            },
        )

        try:
            print_cycle("cycle 1: 同步账户余额并记录快照")
            sync_account_and_position(strategy, client, last_price, last_price)
            recorder.record_snapshot(strategy)
            time.sleep(POLL_SECONDS)

            print_cycle("cycle 2: 创建远离市价的限价买单并记录 open 状态")
            limit_order = client.create_order(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=float(limit_amount),
                price=float(limit_price),
            )
            save_order_once(repository, seen_order_ids, limit_order, run.run_id, strategy.name)
            limit_fetched_order = client.fetch_order(str(limit_order["id"]), SYMBOL)
            update_order_from_exchange(repository, limit_fetched_order, run.run_id)
            sync_account_and_position(strategy, client, last_price, last_price)
            recorder.record_snapshot(strategy)
            time.sleep(POLL_SECONDS)

            print_cycle("cycle 3: 撤销限价单并记录 canceled 状态")
            limit_canceled_order = client.cancel_order(str(limit_order["id"]), SYMBOL)
            update_order_from_exchange(repository, limit_canceled_order, run.run_id)
            sync_account_and_position(strategy, client, last_price, last_price)
            recorder.record_snapshot(strategy)
            time.sleep(POLL_SECONDS)

            print_cycle("cycle 4: 市价买入并写入买入成交和持仓快照")
            buy_order = client.create_order(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=float(buy_amount),
            )
            save_order_once(repository, seen_order_ids, buy_order, run.run_id, strategy.name)
            buy_order = client.fetch_order(str(buy_order["id"]), SYMBOL)
            update_order_from_exchange(repository, buy_order, run.run_id)
            buy_trades = client.fetch_order_trades(str(buy_order["id"]), SYMBOL)
            save_trades_once(repository, seen_trade_ids, buy_trades, run.run_id, strategy.name)
            buy_entry_price = decimal_from_value(buy_order.get("average")) or last_price
            sync_account_and_position(strategy, client, last_price, buy_entry_price)
            recorder.record_snapshot(strategy)
            time.sleep(POLL_SECONDS)

            print_cycle("cycle 5: 市价卖出平仓并写入卖出成交")
            sell_amount = decimal_from_value(buy_order.get("filled")) or decimal_from_balance(client.fetch_balance(), "free", BASE_ASSET)
            sell_order = client.create_order(
                symbol=SYMBOL,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=float(sell_amount),
            )
            save_order_once(repository, seen_order_ids, sell_order, run.run_id, strategy.name)
            sell_order = client.fetch_order(str(sell_order["id"]), SYMBOL)
            update_order_from_exchange(repository, sell_order, run.run_id)
            sell_trades = client.fetch_order_trades(str(sell_order["id"]), SYMBOL)
            save_trades_once(repository, seen_trade_ids, sell_trades, run.run_id, strategy.name)
            sync_account_and_position(strategy, client, last_price, buy_entry_price)
            recorder.record_snapshot(strategy)

            finished_run = recorder.finish_run(strategy)
            orders = repository.get_orders(run.run_id)
            account_snapshots = repository.get_account_snapshots(run.run_id)
            position_snapshots = repository.get_position_snapshots(run.run_id)
            trades = repository.get_trades(run.run_id)
        except Exception:
            if limit_order is not None and limit_canceled_order is None:
                try:
                    client.cancel_order(str(limit_order["id"]), SYMBOL)
                except Exception:
                    pass
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

    print("OKX Demo 周期性实盘记录压力验证完成")
    print(f"symbol: {SYMBOL}")
    print(f"cycles: {CYCLES}")
    print(f"last_price: {last_price}")
    print(f"limit_price: {limit_price}")
    print(f"limit_order_id: {limit_order.get('id') if limit_order else None}")
    print(f"limit_fetched_status: {limit_fetched_order.get('status') if limit_fetched_order else None}")
    print(f"limit_final_status: {limit_canceled_order.get('status') if limit_canceled_order else None}")
    print(f"buy_order_id: {buy_order.get('id') if buy_order else None}")
    print(f"buy_status: {buy_order.get('status') if buy_order else None}")
    print(f"buy_filled: {buy_order.get('filled') if buy_order else None}")
    print(f"sell_order_id: {sell_order.get('id') if sell_order else None}")
    print(f"sell_status: {sell_order.get('status') if sell_order else None}")
    print(f"sell_filled: {sell_order.get('filled') if sell_order else None}")
    print(f"run_id: {finished_run.run_id}")
    print(f"status: {finished_run.status}")
    print(f"orders: {len(orders)}")
    print(f"account_snapshots: {len(account_snapshots)}")
    print(f"position_snapshots: {len(position_snapshots)}")
    print(f"trades: {len(trades)}")


if __name__ == "__main__":
    main()
