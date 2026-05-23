import os
from decimal import Decimal
from getpass import getpass

from crypto_quant.config import BinanceConfig, MySQLConfig
from crypto_quant.database import TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.enums import OrderSide, OrderType, TradingMode
from crypto_quant.exchange import BinanceClient


SYMBOL = "BTC/USDT"
TARGET_NOTIONAL_USDT = Decimal("20")


mysql_config = MySQLConfig(
    host="127.0.0.1",
    port=3306,
    username="crypto_quant_user",
    password=getpass("请输入本地 MySQL 密码："),
    database="crypto_quant",
)

binance_config = BinanceConfig(
    api_key=os.environ["BINANCE_TESTNET_API_KEY"],
    secret=os.environ["BINANCE_TESTNET_SECRET_KEY"],
    trading_mode=TradingMode.SPOT,
    sandbox=True,
    proxies={
        "http": "socks5h://127.0.0.1:1080",
        "https": "socks5h://127.0.0.1:1080",
    },
)


def main() -> None:
    client = BinanceClient(binance_config)
    client.load_markets()
    ticker = client.exchange.fetch_ticker(SYMBOL)
    last_price = Decimal(str(ticker["last"] or ticker["close"]))
    order_price = last_price * Decimal("0.8")
    amount = TARGET_NOTIONAL_USDT / order_price

    mysql_engine = create_mysql_engine(mysql_config)
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)

    created_order = None
    fetched_order = None
    canceled_order = None

    with Session() as session:
        repository = TradingRepository(session)
        run = repository.create_run(
            name="binance_spot_testnet_order_record",
            run_type="testnet_order",
            trading_mode=TradingMode.SPOT.value,
            strategy_name="manual_testnet_order",
            symbols=[SYMBOL],
            initial_cash=TARGET_NOTIONAL_USDT,
            config={
                "source": "examples/run_testnet_order_recorder.py",
                "exchange": "binance_spot_testnet",
                "symbol": SYMBOL,
                "sandbox": True,
                "target_notional_usdt": TARGET_NOTIONAL_USDT,
            },
        )

        try:
            created_order = client.create_order(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                amount=float(amount),
                price=float(order_price),
            )
            order_record = repository.save_order(
                created_order,
                trading_mode=TradingMode.SPOT.value,
                run_id=run.run_id,
                strategy_name="manual_testnet_order",
            )

            fetched_order = client.fetch_order(str(created_order["id"]), SYMBOL)
            repository.update_order_status(
                str(created_order["id"]),
                fetched_order.get("status", order_record.status),
                run_id=run.run_id,
                filled=Decimal(str(fetched_order.get("filled") or "0")),
                average=Decimal(str(fetched_order["average"])) if fetched_order.get("average") is not None else None,
            )

            canceled_order = client.cancel_order(str(created_order["id"]), SYMBOL)
            final_status = canceled_order.get("status") or "canceled"
            repository.update_order_status(
                str(created_order["id"]),
                final_status,
                run_id=run.run_id,
                filled=Decimal(str(canceled_order.get("filled") or fetched_order.get("filled") or "0")),
                average=Decimal(str(canceled_order["average"])) if canceled_order.get("average") is not None else None,
            )
            finished_run = repository.finish_run(run.run_id, final_equity=TARGET_NOTIONAL_USDT, status="finished")
            orders = repository.get_orders(run.run_id)
        except Exception:
            if created_order is not None:
                try:
                    client.cancel_order(str(created_order["id"]), SYMBOL)
                except Exception:
                    pass
            repository.finish_run(run.run_id, final_equity=TARGET_NOTIONAL_USDT, status="failed")
            raise

    print("Binance Spot Testnet 订单状态入库完成")
    print(f"symbol: {SYMBOL}")
    print(f"last_price: {last_price}")
    print(f"order_price: {order_price}")
    print(f"amount: {amount}")
    print(f"exchange_order_id: {created_order.get('id') if created_order else None}")
    print(f"created_status: {created_order.get('status') if created_order else None}")
    print(f"fetched_status: {fetched_order.get('status') if fetched_order else None}")
    print(f"canceled_status: {canceled_order.get('status') if canceled_order else None}")
    print(f"run_id: {finished_run.run_id}")
    print(f"run_type: {finished_run.run_type}")
    print(f"status: {finished_run.status}")
    print(f"orders: {len(orders)}")


if __name__ == "__main__":
    main()