import os

from crypto_quant.config import ExchangeConfig
from crypto_quant.enums import TradingMode
from crypto_quant.exchange import ExchangeClient


okx_config = ExchangeConfig(
    api_key=os.environ["OKX_DEMO_API_KEY"],
    secret=os.environ["OKX_DEMO_SECRET_KEY"],
    password=os.environ["OKX_DEMO_PASSPHRASE"],
    trading_mode=TradingMode.SPOT,
    sandbox=True,
)


def main() -> None:
    client = ExchangeClient(okx_config)
    markets = client.load_markets()
    balance = client.fetch_balance()

    print("OKX Demo 连通性验证完成")
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
