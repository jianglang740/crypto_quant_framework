import ccxt.pro
import asyncio

async def watch_orderbook():
    proxy_uri = "socks5h://127.0.0.1:1080"
    exchange = ccxt.pro.binance({
        'proxies': {'http': proxy_uri, 'https': proxy_uri},
        'wsProxy': proxy_uri,   # ✅ CCXT Pro websocket单独代理，之前缺这个是关键坑
        'enableRateLimit': True,
        'timeout': 15000,
        'options': {
            'defaultType': 'spot',
            # 强制全路径锁定现货，彻底屏蔽dapi/fapi
            'api': {
                'spot': {
                    'rest': 'https://api.binance.com',
                    'ws': 'wss://stream.binance.com:9443'
                }
            }
        }
    })

    # ✅ 关键：初始化立刻加载现货市场，阻断ccxt自动遍历合约域名
    await exchange.load_markets()
    symbol = 'BTC/USDT'
    limit = 10
    print(f"市场加载完成，共{len(exchange.markets)}个交易对")

    while True:
        try:
            orderbook = await exchange.watch_order_book(symbol, limit=limit)
            bid_p, bid_q = orderbook['bids'][0]
            ask_p, ask_q = orderbook['asks'][0]
            print(f"买一 {bid_p:8.2f} {bid_q:.4f} | 卖一 {ask_p:8.2f} {ask_q:.4f}")
        except Exception as e:
            print(f"异常:{str(e)},等待3s")
            await asyncio.sleep(3)

if __name__ == '__main__':
    asyncio.run(watch_orderbook())