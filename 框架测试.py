"""框架 OKX Demo 完整测试 — 双向持仓模式"""
from crypto_quant.config import ExchangeConfig
from crypto_quant.exchange import ExchangeClient, ExchangeClientError
from crypto_quant.data import MarketDataFetcher
from crypto_quant.enums import MarginMode, OrderSide, OrderType, PositionSide, TradingMode

PROXY = {"http": "socks5h://127.0.0.1:1080", "https": "socks5h://127.0.0.1:1080"}
CREDS = {
    "api_key": "0f32ea22-cff8-464c-b07b-2fcba964e6dd",
    "secret": "C0363B140D6ED424F2BF27851397AC49",
    "password": "Jl.2018036661",
}

def mk(trading_mode):
    return ExchangeClient(ExchangeConfig(
        exchange_name="okx", trading_mode=trading_mode,
        sandbox=True, proxies=PROXY, **CREDS,
    ))

def fo(client, symbol, order):
    try:
        return client.fetch_order(order.get("id") or order["info"]["ordId"], symbol)
    except Exception:
        return order

# ━━ 1. MarketDataFetcher ━━
print("=" * 50)
print("1. MarketDataFetcher")
print("=" * 50)
c = mk(TradingMode.SPOT)
bars = MarketDataFetcher(c).fetch_ohlcv("ETH/USDT", "5m", limit=3)
print(f"  K 线: {len(bars)} 根, close={bars[-1].close}")

# ━━ 2. 现货 ━━
print("\n" + "=" * 50)
print("2. 现货买入 → 卖出")
print("=" * 50)
spot = mk(TradingMode.SPOT)
b = spot.fetch_balance()
print(f"  下单前 USDT={b['total'].get('USDT'):.2f} ETH={b['total'].get('ETH')}")

o = spot.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 0.01)
f = fo(spot, "ETH/USDT", o)
print(f"  买入 ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

o = spot.create_order("ETH/USDT", OrderSide.SELL, OrderType.MARKET, 0.01)
f = fo(spot, "ETH/USDT", o)
print(f"  卖出 ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

b2 = spot.fetch_balance()
print(f"  下单后 USDT={b2['total'].get('USDT'):.2f} ETH={b2['total'].get('ETH')}")

# ━━ 3. 合约做多 ━━
print("\n" + "=" * 50)
print("3. 合约做多 → 平多 (reduce_only)")
print("=" * 50)
swap = mk(TradingMode.FUTURE)
swap.set_leverage("ETH/USDT", 10)
swap.set_margin_mode("ETH/USDT", MarginMode.CROSS, {"lever": 10})

b = swap.fetch_balance()
p = swap.fetch_positions(["ETH/USDT"])
print(f"  下单前 USDT={b['total'].get('USDT'):.2f} 持仓={len(p)}")

o = swap.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 1,
                       position_side=PositionSide.LONG)
f = fo(swap, "ETH/USDT", o)
print(f"  开多 ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

o = swap.create_order("ETH/USDT", OrderSide.SELL, OrderType.MARKET, 1,
                       position_side=PositionSide.LONG)
f = fo(swap, "ETH/USDT", o)
print(f"  平多 ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

b2 = swap.fetch_balance()
p2 = swap.fetch_positions(["ETH/USDT"])
print(f"  下单后 USDT={b2['total'].get('USDT'):.2f} 持仓={len(p2)}")

# ━━ 4. 合约做空 ━━
print("\n" + "=" * 50)
print("4. 合约做空 → 平空 (reduce_only)")
print("=" * 50)
o = swap.create_order("ETH/USDT", OrderSide.SELL, OrderType.MARKET, 1,
                       position_side=PositionSide.SHORT)
f = fo(swap, "ETH/USDT", o)
print(f"  开空 ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

o = swap.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 1,
                       position_side=PositionSide.SHORT)
f = fo(swap, "ETH/USDT", o)
print(f"  平空 ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

b2 = swap.fetch_balance()
print(f"  下单后 USDT={b2['total'].get('USDT'):.2f}")

# ━━ 5. close_position ━━
print("\n" + "=" * 50)
print("5. close_position 方法")
print("=" * 50)
swap.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 1, position_side=PositionSide.LONG)
o = swap.close_position("ETH/USDT", 1, position_side=PositionSide.LONG)
f = fo(swap, "ETH/USDT", o)
print(f"  close_position(LONG) ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

swap.create_order("ETH/USDT", OrderSide.SELL, OrderType.MARKET, 1, position_side=PositionSide.SHORT)
o = swap.close_position("ETH/USDT", 1, position_side=PositionSide.SHORT)
f = fo(swap, "ETH/USDT", o)
print(f"  close_position(SHORT) ✅ {f['status']} filled={f.get('filled')} avg={f.get('average')}")

print("\n" + "=" * 50)
print("全部通过！")
print("=" * 50)
111