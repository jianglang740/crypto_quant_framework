import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.config import BinanceConfig, MySQLConfig
from crypto_quant.database import TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.database.models import TradeRecord
from crypto_quant.enums import OrderSide, OrderType, PositionSide, TradingMode
from crypto_quant.exchange import BinanceClient
from crypto_quant.strategy.base import Account, Position, StrategyBase

SYMBOL = os.getenv("TESTNET_SYMBOL", "BTC/USDT")
BASE_ASSET = os.getenv("TESTNET_BASE_ASSET", SYMBOL.split("/")[0])
QUOTE_ASSET = os.getenv("TESTNET_QUOTE_ASSET", SYMBOL.split("/")[1])
TRADE_NOTIONAL_USDT = Decimal(os.getenv("TESTNET_TRADE_NOTIONAL_USDT", "20"))
SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("TESTNET_SNAPSHOT_INTERVAL_SECONDS", "30"))
HOLD_SNAPSHOTS = int(os.getenv("TESTNET_HOLD_SNAPSHOTS", "2"))
MAX_CYCLES = int(os.getenv("TESTNET_MAX_CYCLES", "0"))
RUN_ID = os.getenv("TESTNET_RUN_ID") or f"testnet_smoke_{datetime.now():%Y%m%d_%H%M%S}"


class TestnetSmokeStrategy(StrategyBase):
    name = "testnet_smoke_strategy"


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        username=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "crypto_quant"),
    )


def binance_config_from_env() -> BinanceConfig:
    proxies = None
    proxy_url = os.getenv("BINANCE_PROXY_URL")
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    return BinanceConfig(
        api_key=os.environ["BINANCE_TESTNET_API_KEY"],
        secret=os.environ["BINANCE_TESTNET_SECRET_KEY"],
        trading_mode=TradingMode.SPOT,
        sandbox=True,
        proxies=proxies,
    )


def decimal_from_value(value) -> Decimal:
    return Decimal(str(value or "0"))


def decimal_from_balance(balance: dict, group: str, asset: str) -> Decimal:
    return Decimal(str(balance.get(group, {}).get(asset, 0)))


def datetime_from_milliseconds(value) -> datetime:
    if value is None:
        return datetime.utcnow()
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)


def latest_price(client: BinanceClient) -> Decimal:
    ticker = client.exchange.fetch_ticker(SYMBOL)
    return decimal_from_value(ticker.get("last") or ticker.get("close"))


def trade_key(trade: dict) -> str:
    trade_id = trade.get("id")
    if trade_id is not None:
        return f"trade:{trade_id}"
    return json.dumps(
        {
            "order": trade.get("order"),
            "timestamp": trade.get("timestamp"),
            "side": trade.get("side"),
            "amount": trade.get("amount"),
            "price": trade.get("price"),
        },
        sort_keys=True,
        default=str,
    )


def trade_record_from_ccxt(
    trade: dict,
    run_id: str,
    strategy_name: str,
    realized_pnl: Decimal | None = None,
) -> TradeRecord:
    fee = trade.get("fee") or {}
    return TradeRecord(
        run_id=run_id,
        strategy_name=strategy_name,
        exchange="binance_testnet",
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
        realized_pnl=realized_pnl,
        traded_at=datetime_from_milliseconds(trade.get("timestamp")),
        raw=json.dumps(trade, ensure_ascii=False, default=str),
    )


def sync_account_and_position(
    strategy: StrategyBase,
    client: BinanceClient,
    mark_price: Decimal,
    entry_price: Decimal | None,
    raw_balance: dict | None = None,
) -> dict:
    balance = raw_balance or client.fetch_balance()
    base_free = decimal_from_balance(balance, "free", BASE_ASSET)
    quote_free = decimal_from_balance(balance, "free", QUOTE_ASSET)
    quote_total = decimal_from_balance(balance, "total", QUOTE_ASSET)
    position_value = base_free * mark_price
    unrealized_pnl = Decimal("0") if entry_price is None else (mark_price - entry_price) * base_free

    strategy.account = Account(
        cash=quote_total,
        equity=quote_total + position_value,
        available=quote_free,
        unrealized_pnl=unrealized_pnl,
    )
    if base_free > Decimal("0"):
        strategy.positions = {
            f"{SYMBOL}:{PositionSide.BOTH.value}": Position(
                symbol=SYMBOL,
                side=PositionSide.BOTH,
                amount=base_free,
                entry_price=entry_price or mark_price,
                mark_price=mark_price,
                unrealized_pnl=unrealized_pnl,
            )
        }
    else:
        strategy.positions = {}
    return balance


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
    repository.save_order(order, trading_mode=TradingMode.SPOT.value, run_id=run_id, strategy_name=strategy_name)
    seen_order_ids.add(order_id)


def update_order_from_exchange(repository: TradingRepository, order: dict, run_id: str) -> None:
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
    realized_pnl: Decimal | None = None,
) -> int:
    saved_count = 0
    for trade in trades:
        key = trade_key(trade)
        if key in seen_trade_ids:
            continue
        repository.save_trade(trade_record_from_ccxt(trade, run_id, strategy_name, realized_pnl=realized_pnl))
        seen_trade_ids.add(key)
        saved_count += 1
    return saved_count


def record_snapshot(repository: TradingRepository, strategy: StrategyBase, run_id: str) -> None:
    repository.save_live_snapshot(strategy, run_id, timestamp=datetime.utcnow())


def create_market_order(client: BinanceClient, side: OrderSide, amount: Decimal) -> dict:
    return client.create_order(
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.MARKET,
        amount=float(amount),
    )


def main() -> None:
    client = BinanceClient(binance_config_from_env())
    client.load_markets()

    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)

    strategy = TestnetSmokeStrategy(trading_mode=TradingMode.SPOT)
    seen_order_ids: set[str] = set()
    seen_trade_ids: set[str] = set()
    entry_price: Decimal | None = None
    hold_counter = 0
    cycle = 0

    with Session() as session:
        repository = TradingRepository(session)
        price = latest_price(client)
        sync_account_and_position(strategy, client, price, entry_price)
        run = repository.create_run(
            run_id=RUN_ID,
            name="binance_spot_testnet_smoke_strategy",
            run_type="testnet",
            trading_mode=TradingMode.SPOT.value,
            strategy_name=strategy.name,
            symbols=[SYMBOL],
            timeframe=f"snapshot_{SNAPSHOT_INTERVAL_SECONDS}s",
            initial_cash=strategy.account.cash,
            config={
                "source": "real/run_testnet_smoke_strategy.py",
                "exchange": "binance_spot_testnet",
                "symbol": SYMBOL,
                "sandbox": True,
                "trade_notional_usdt": str(TRADE_NOTIONAL_USDT),
                "snapshot_interval_seconds": SNAPSHOT_INTERVAL_SECONDS,
                "hold_snapshots": HOLD_SNAPSHOTS,
                "max_cycles": MAX_CYCLES,
            },
        )
        print(f"started testnet smoke run: run_id={run.run_id}, symbol={SYMBOL}")

        try:
            while MAX_CYCLES <= 0 or cycle < MAX_CYCLES:
                cycle += 1
                price = latest_price(client)
                balance = sync_account_and_position(strategy, client, price, entry_price)
                base_free = decimal_from_balance(balance, "free", BASE_ASSET)
                quote_free = decimal_from_balance(balance, "free", QUOTE_ASSET)

                if base_free <= Decimal("0") and quote_free >= TRADE_NOTIONAL_USDT:
                    buy_amount = TRADE_NOTIONAL_USDT / price
                    order = create_market_order(client, OrderSide.BUY, buy_amount)
                    save_order_once(repository, seen_order_ids, order, run.run_id, strategy.name)
                    fetched_order = client.fetch_order(str(order["id"]), SYMBOL)
                    update_order_from_exchange(repository, fetched_order, run.run_id)
                    trades = client.fetch_order_trades(str(order["id"]), SYMBOL)
                    save_trades_once(repository, seen_trade_ids, trades, run.run_id, strategy.name)
                    entry_price = decimal_from_value(fetched_order.get("average")) or price
                    hold_counter = 0
                    print(f"[{datetime.now():%F %T}] buy filled={fetched_order.get('filled')} avg={fetched_order.get('average')}")
                elif base_free > Decimal("0"):
                    hold_counter += 1
                    if hold_counter >= HOLD_SNAPSHOTS:
                        sell_amount = base_free
                        order = create_market_order(client, OrderSide.SELL, sell_amount)
                        save_order_once(repository, seen_order_ids, order, run.run_id, strategy.name)
                        fetched_order = client.fetch_order(str(order["id"]), SYMBOL)
                        update_order_from_exchange(repository, fetched_order, run.run_id)
                        exit_price = decimal_from_value(fetched_order.get("average")) or price
                        realized_pnl = None if entry_price is None else (exit_price - entry_price) * decimal_from_value(fetched_order.get("filled"))
                        trades = client.fetch_order_trades(str(order["id"]), SYMBOL)
                        save_trades_once(repository, seen_trade_ids, trades, run.run_id, strategy.name, realized_pnl=realized_pnl)
                        entry_price = None
                        hold_counter = 0
                        print(f"[{datetime.now():%F %T}] sell filled={fetched_order.get('filled')} avg={fetched_order.get('average')}")

                price = latest_price(client)
                sync_account_and_position(strategy, client, price, entry_price)
                record_snapshot(repository, strategy, run.run_id)
                print(f"[{datetime.now():%F %T}] snapshot cycle={cycle} equity={strategy.account.equity} positions={len(strategy.positions)}")
                time.sleep(SNAPSHOT_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="stopped")
            print(f"stopped testnet smoke run: run_id={run.run_id}")
            return
        except Exception:
            repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="failed")
            raise

        repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="finished")
        print(f"finished testnet smoke run: run_id={run.run_id}")


if __name__ == "__main__":
    main()