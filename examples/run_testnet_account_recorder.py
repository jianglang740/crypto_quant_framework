import os
from decimal import Decimal
from getpass import getpass

from crypto_quant.config import BinanceConfig, MySQLConfig
from crypto_quant.database import LiveDatabaseRecorder, TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.enums import TradingMode
from crypto_quant.exchange import BinanceClient
from crypto_quant.strategy.base import Account, StrategyBase


class TestnetAccountSnapshotStrategy(StrategyBase):
    name = "testnet_account_snapshot"


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


def decimal_from_balance(balance: dict, group: str, asset: str) -> Decimal:
    return Decimal(str(balance.get(group, {}).get(asset, 0)))


def main() -> None:
    client = BinanceClient(binance_config)
    client.load_markets()
    balance = client.fetch_balance()

    usdt_free = decimal_from_balance(balance, "free", "USDT")
    usdt_used = decimal_from_balance(balance, "used", "USDT")
    usdt_total = decimal_from_balance(balance, "total", "USDT")

    strategy = TestnetAccountSnapshotStrategy(trading_mode=TradingMode.SPOT)
    strategy.account = Account(
        cash=usdt_total,
        equity=usdt_total,
        available=usdt_free,
        margin=usdt_used,
    )

    mysql_engine = create_mysql_engine(mysql_config)
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)

    with Session() as session:
        repository = TradingRepository(session)
        recorder = LiveDatabaseRecorder(
            repository,
            run_name="binance_spot_testnet_account_snapshot",
            exchange="binance_testnet",
        )
        run = recorder.start_run(
            strategy,
            symbols=["BTC/USDT"],
            config={
                "source": "examples/run_testnet_account_recorder.py",
                "exchange": "binance_spot_testnet",
                "asset": "USDT",
                "sandbox": True,
            },
        )
        recorder.record_snapshot(strategy)
        finished_run = recorder.finish_run(strategy)
        account_snapshots = repository.get_account_snapshots(run.run_id)

    print("Binance Spot Testnet 账户快照入库完成")
    print(f"USDT free: {usdt_free}")
    print(f"USDT used: {usdt_used}")
    print(f"USDT total: {usdt_total}")
    print(f"run_id: {finished_run.run_id}")
    print(f"run_name: {finished_run.name}")
    print(f"run_type: {finished_run.run_type}")
    print(f"status: {finished_run.status}")
    print(f"final_equity: {finished_run.final_equity}")
    print(f"account_snapshots: {len(account_snapshots)}")


if __name__ == "__main__":
    main()