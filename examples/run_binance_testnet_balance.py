import os

from crypto_quant.config import BinanceConfig
from crypto_quant.enums import TradingMode
from crypto_quant.exchange import BinanceClient


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
    markets = client.load_markets()
    balance = client.fetch_balance()

    print("Binance Spot Testnet 连通性验证完成")
    print(f"市场数量: {len(markets)}")

    total = balance.get("total", {})
    free = balance.get("free", {})
    used = balance.get("used", {})
    assets = sorted(asset for asset, amount in total.items() if amount)

    print("非零资产:")
    for asset in assets:
        print(
            f"{asset}: "
            f"free={free.get(asset, 0)}, "
            f"used={used.get(asset, 0)}, "
            f"total={total.get(asset, 0)}"
        )


if __name__ == "__main__":
    main()
