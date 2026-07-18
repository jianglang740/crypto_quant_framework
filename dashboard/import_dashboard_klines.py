from __future__ import annotations

import argparse
import os
from datetime import timezone
from pathlib import Path

from crypto_quant.config import MySQLConfig
from crypto_quant.data.csv_loader import load_bars_from_csv
from crypto_quant.data.time_utils import BEIJING_TIMEZONE
from crypto_quant.database import MarketDataRepository, create_all_tables, create_mysql_engine, create_session_factory


def main() -> None:
    args = parse_args()
    data_feed = load_bars_from_csv(
        path=args.csv,
        symbol=args.symbol,
        timeframe=args.timeframe,
        datetime_column=args.datetime_column,
        open_column=args.open_column,
        high_column=args.high_column,
        low_column=args.low_column,
        close_column=args.close_column,
        volume_column=args.volume_column,
        source_timezone=parse_timezone(args.source_timezone),
        target_timezone=parse_timezone(args.target_timezone),
        drop_timezone=args.drop_timezone,
        validate=not args.skip_validate,
        raise_on_missing=args.raise_on_missing,
    )

    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)
    with Session() as session:
        repository = MarketDataRepository(session)
        repository.upsert_klines(data_feed.bars, exchange=args.exchange)

    first_time = data_feed.bars[0].datetime if data_feed.bars else None
    last_time = data_feed.bars[-1].datetime if data_feed.bars else None
    print("dashboard klines imported successfully")
    print(f"symbol={args.symbol}")
    print(f"timeframe={args.timeframe}")
    print(f"exchange={args.exchange}")
    print(f"bars={len(data_feed.bars)}")
    print(f"first={first_time}")
    print(f"last={last_time}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import CSV klines into MySQL for dashboard market charts.")
    parser.add_argument("--csv", required=True, type=Path, help="CSV file path.")
    parser.add_argument("--symbol", default="ETH/USDT", help="Trading symbol, for example ETH/USDT.")
    parser.add_argument("--timeframe", default="5m", help="Kline timeframe, for example 1m, 5m, 15m, 1h.")
    parser.add_argument("--exchange", default="okx", help="Exchange name saved to klines.exchange.")
    parser.add_argument("--datetime-column", default="datetime")
    parser.add_argument("--open-column", default="open")
    parser.add_argument("--high-column", default="high")
    parser.add_argument("--low-column", default="low")
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--volume-column", default="volume")
    parser.add_argument("--source-timezone", default="Asia/Shanghai", choices=["Asia/Shanghai", "UTC"])
    parser.add_argument("--target-timezone", default="Asia/Shanghai", choices=["Asia/Shanghai", "UTC"])
    parser.add_argument("--drop-timezone", action="store_true", help="Drop timezone info before saving.")
    parser.add_argument("--skip-validate", action="store_true", help="Skip kline cleaning and continuity validation.")
    parser.add_argument("--raise-on-missing", action="store_true", help="Raise if missing kline intervals are detected.")
    return parser.parse_args()


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE", "crypto_quant"),
    )


def parse_timezone(value: str) -> timezone:
    if value == "UTC":
        return timezone.utc
    return BEIJING_TIMEZONE


if __name__ == "__main__":
    main()
