import ccxt
import time

PROXY = {"http": "socks5h://127.0.0.1:1080", "https": "socks5h://127.0.0.1:1080"}
CREDS = {
    "apiKey": "0f32ea22-cff8-464c-b07b-2fcba964e6dd",
    "secret": "C0363B140D6ED424F2BF27851397AC49",
    "password": "Jl.2018036661",
}

# ── 查询余额 ──
ex = ccxt.okx({**CREDS, "enableRateLimit": True, "proxies": PROXY})
ex.set_sandbox_mode(True)

print("=== 下单前余额 ===")
spot_bal = ex.fetch_balance({"type": "spot"})
swap_bal = ex.fetch_balance({"type": "swap"})
print(f"现货 USDT: {spot_bal['total'].get('USDT')}")
print(f"合约 USDT: {swap_bal['total'].get('USDT')}")


'''
#现货市价单
ex.options["defaultType"] = "spot"
order = ex.create_order(
    symbol="BTC/USDT",
    type="market",
    side="buy",
    amount=0.0001,
    )
print(f"create_order 返回: {order}")

# ccxt OKX 批量下单接口不返回 status，需要单独查
fetched = ex.fetch_order(order["id"], "BTC/USDT")
print(f"订单ID: {fetched['id']}  状态: {fetched['status']}  成交: {fetched.get('filled')}  均价: {fetched.get('average')}")
'''

#合约市价单

order = ex.create_order(
    symbol="BTC/USDT:USDT",
    type="market",
    side="buy",
    amount=100,
    params={"positionSide": "long", "leverage": 100},
    )

print("=== 下单后余额 ===")
spot_bal = ex.fetch_balance({"type": "spot"})
swap_bal = ex.fetch_balance({"type": "swap"})
print(f"现货 USDT: {spot_bal['total'].get('USDT')}")
print(f"合约 USDT: {swap_bal['total'].get('USDT')}")
