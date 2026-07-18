"""测试 cover/close_position 能否真正平掉 OKX 仓位"""
import time
from decimal import Decimal
from crypto_quant.config import ExchangeConfig
from crypto_quant.exchange import ExchangeClient
from crypto_quant.enums import MarginMode, OrderSide, OrderType, PositionSide, TradingMode

PROXY = {"http": "socks5h://127.0.0.1:1080", "https": "socks5h://127.0.0.1:1080"}

swap = ExchangeClient(ExchangeConfig(
    exchange_name="okx",
    api_key="0f32ea22-cff8-464c-b07b-2fcba964e6dd",
    secret="C0363B140D6ED424F2BF27851397AC49",
    password="Jl.2018036661",
    trading_mode=TradingMode.FUTURE, sandbox=True, proxies=PROXY,
))
swap.set_leverage("ETH/USDT", 10)
swap.set_margin_mode("ETH/USDT", MarginMode.CROSS, {"lever": 10})


def wait_for_positions(symbol, expect_count=1, timeout=5.0, label=""):
    """等待持仓数据可用，超时返回空列表"""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        positions = swap.fetch_positions([symbol])
        if len(positions) >= expect_count:
            return positions
        time.sleep(0.5)
    return swap.fetch_positions([symbol])


def show_balance(label):
    b = swap.fetch_balance()
    total = b['total'].get('USDT', 0)
    print(f"  [{label}] 合约 USDT: {total:.2f}  (Δ {float(total) - show_balance.last:.2f})")
    show_balance.last = float(total)
show_balance.last = 0

def show_positions(label):
    positions = swap.fetch_positions(["ETH/USDT"])
    if not positions:
        print(f"  [{label}] 持仓: 无 (OKX demo positions API 不可靠，以订单状态和余额为准)")
        return
    for p in positions:
        print(f"  [{label}] {p['side']} {p['contracts']}张 均价={p['entryPrice']}")


# ━━ 1. 开多 → close_position 平多 ━━
print("=== 测试1: close_position(LONG) 平多 ===")
print("开多 1 张 ...")
o = swap.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 1, position_side=PositionSide.LONG)
print(f"  订单: {swap.fetch_order(o['id'], 'ETH/USDT')['status']}")
show_positions("开多后"); show_balance("开多后")

print("close_position(LONG) 平多 ...")
o = swap.close_position("ETH/USDT", 1, position_side=PositionSide.LONG)
print(f"  订单: {swap.fetch_order(o['id'], 'ETH/USDT')['status']}")
show_positions("平多后"); show_balance("平多后")

# ━━ 2. 开空 → cover 平空 ━━
print("\n=== 测试2: cover 平空 ===")
print("开空 1 张 ...")
o = swap.create_order("ETH/USDT", OrderSide.SELL, OrderType.MARKET, 1, position_side=PositionSide.SHORT)
print(f"  订单: {swap.fetch_order(o['id'], 'ETH/USDT')['status']}")
show_positions("开空后"); show_balance("开空后")

print("cover: buy + position_side=SHORT ...")
o = swap.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 1, position_side=PositionSide.SHORT)
print(f"  订单: {swap.fetch_order(o['id'], 'ETH/USDT')['status']}")
show_positions("平空后"); show_balance("平空后")

# ━━ 3. StrategyBase 完整链路 ━━
print("\n=== 测试3: StrategyBase 完整链路 ===")
from crypto_quant.strategy.base import StrategyBase
from crypto_quant.engine.live import LiveEngine
from crypto_quant.config import LiveConfig

class TestStrategy(StrategyBase):
    name = "test_close"

s = TestStrategy(trading_mode=TradingMode.FUTURE)
eng = LiveEngine(swap, LiveConfig(dry_run=False, sync_on_start=False))
s.bind_engine(eng)

swap.create_order("ETH/USDT", OrderSide.BUY, OrderType.MARKET, 1, position_side=PositionSide.LONG)
show_positions("开多后"); show_balance("开多后")

s.close_position("ETH/USDT", PositionSide.LONG)
show_positions("strategy平多后"); show_balance("strategy平多后")

swap.create_order("ETH/USDT", OrderSide.SELL, OrderType.MARKET, 1, position_side=PositionSide.SHORT)
show_positions("开空后"); show_balance("开空后")

s.cover("ETH/USDT", Decimal("1"))
show_positions("strategy平空后"); show_balance("strategy平空后")

print("\n✅ 全部测试完成")
