from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.config import ExchangeConfig, MySQLConfig
from crypto_quant.data.fetcher import MarketDataFetcher
from crypto_quant.data.time_utils import BEIJING_TIMEZONE
from crypto_quant.database import MarketDataRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.enums import KlineInterval, TradingMode
from crypto_quant.exchange import ExchangeClient

SYMBOL = "BTC/USDT"
TIMEFRAME = KlineInterval.M5
DAYS = 5
EXCHANGE = "okx"
REQUEST_INTERVAL_SECONDS = 0.2


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT") or os.getenv("MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME") or os.getenv("MYSQL_USER", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", "crypto_quant"),
    )


def okx_config_from_env() -> ExchangeConfig:
    proxy_url = os.getenv("CRYPTO_QUANT_OKX_PROXY_URL") or os.getenv("OKX_PROXY_URL")
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    return ExchangeConfig(
        api_key=os.getenv("CRYPTO_QUANT_OKX_API_KEY") or os.getenv("OKX_API_KEY", ""),
        secret=os.getenv("CRYPTO_QUANT_OKX_SECRET_KEY") or os.getenv("OKX_SECRET_KEY", ""),
        password=os.getenv("CRYPTO_QUANT_OKX_PASSPHRASE") or os.getenv("OKX_PASSPHRASE", ""),
        trading_mode=TradingMode.SPOT,
        sandbox=False,
        proxies=proxies,
    )


def main() -> None:
    end = datetime.now(BEIJING_TIMEZONE)
    start = end - timedelta(days=DAYS)

    client = ExchangeClient(okx_config_from_env())
    client.load_markets()
    fetcher = MarketDataFetcher(client)
    bars = fetcher.fetch_ohlcv_range(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start=start,
        end=end,
        limit=1000,
        request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        target_timezone=BEIJING_TIMEZONE,
        input_timezone=BEIJING_TIMEZONE,
        drop_timezone=True,
    )

    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)
    with Session() as session:
        repository = MarketDataRepository(session)
        repository.upsert_klines(bars, exchange=EXCHANGE)

    first_time = bars[0].datetime if bars else None
    last_time = bars[-1].datetime if bars else None
    print("btc recent klines imported successfully")
    print(f"symbol={SYMBOL}")
    print(f"timeframe={TIMEFRAME.value}")
    print(f"exchange={EXCHANGE}")
    print(f"days={DAYS}")
    print(f"bars={len(bars)}")
    print(f"first={first_time}")
    print(f"last={last_time}")


if __name__ == "__main__":
    main()
