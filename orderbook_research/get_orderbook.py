"""
订单簿重建与流动性分析研究脚本

功能：
1. 用REST 快照初始化本地订单簿
2. 用WebSocket-client 增量流实时维护订单簿
3. 每次更新后计算流动性指标并打印

代理说明（我的研究环境为本地Mac电脑，需要借助ssh隧道使用我的腾讯东京节点云服务器翻墙）：
1. 启动 SSH 隧道：ssh -fN quant-proxy
2. 将PROXY 改为 "socks5h://127.0.0.1:1080"
"""

import json
import queue
import threading
import time
from dataclasses import dataclass, field

import requests
import websocket

SYMBOL = "btcusdt"
SYMBOL_UPPER = SYMBOL.upper()
DEPTH_LEVELS = 5  # 计算流动性指标时考虑的档位数量
SNAPSHOT_URL = f"https://fapi.binance.com/fapi/v1/depth?symbol={SYMBOL_UPPER}&limit=1000"
WS_URL = f"wss://fstream.binance.com/ws/{SYMBOL}@depth"

# 代理设置：本地开 SSH 隧道时填入，不需要时置空即可（例如上云操作时）
PROXY = "socks5h://127.0.0.1:1080"  


# ─────────────────────────────────────────────
# 本地订单簿
# ─────────────────────────────────────────────

class LocalOrderBook:
    def __init__(self) -> None:
        self.bids: dict[str, float] = {}
        self.asks: dict[str, float] = {}
        self.last_update_id: int = 0

    def apply_snapshot(self, snapshot: dict) -> None:
        self.bids = {p: float(q) for p, q in snapshot["bids"]}
        self.asks = {p: float(q) for p, q in snapshot["asks"]}
        self.last_update_id = snapshot["lastUpdateId"]

    def apply_update(self, bids_diff: list, asks_diff: list, update_id: int) -> None:
        self._apply_side(self.bids, bids_diff)
        self._apply_side(self.asks, asks_diff)
        self.last_update_id = update_id

    @staticmethod
    def _apply_side(side: dict[str, float], diff: list) -> None:
        for price_str, qty_str in diff:
            qty = float(qty_str)
            if qty == 0.0:
                side.pop(price_str, None)
            else:
                side[price_str] = qty

    def sorted_bids(self) -> list[tuple[float, float]]:
        return sorted(((float(p), q) for p, q in self.bids.items()), reverse=True)

    def sorted_asks(self) -> list[tuple[float, float]]:
        return sorted((float(p), q) for p, q in self.asks.items())


# ─────────────────────────────────────────────
# 流动性指标
# ─────────────────────────────────────────────

@dataclass
class LiquidityMetrics:
    best_bid: float
    best_ask: float
    spread: float
    spread_bps: float
    mid_price: float
    weighted_mid: float
    bid_depth: float
    ask_depth: float
    obi: float
    timestamp: float = field(default_factory=time.time)


def compute_metrics(ob: LocalOrderBook, levels: int = DEPTH_LEVELS) -> LiquidityMetrics | None:
    bids = ob.sorted_bids()
    asks = ob.sorted_asks()
    if not bids or not asks:
        return None

    best_bid_p, best_bid_q = bids[0]
    best_ask_p, best_ask_q = asks[0]
    spread = best_ask_p - best_bid_p
    mid = (best_bid_p + best_ask_p) / 2
    weighted_mid = (best_bid_p * best_ask_q + best_ask_p * best_bid_q) / (best_bid_q + best_ask_q)
    bid_depth = sum(q for _, q in bids[:levels])
    ask_depth = sum(q for _, q in asks[:levels])
    total = bid_depth + ask_depth

    return LiquidityMetrics(
        best_bid=best_bid_p,
        best_ask=best_ask_p,
        spread=spread,
        spread_bps=spread / mid * 10000,
        mid_price=mid,
        weighted_mid=weighted_mid,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        obi=bid_depth / total if total > 0 else 0.5,
    )


def print_metrics(m: LiquidityMetrics) -> None:
    pressure = "买压" if m.weighted_mid < m.mid_price else "卖压"
    obi_label = "买强" if m.obi > 0.6 else ("卖强" if m.obi < 0.4 else "均衡")
    print(
        f"bid={m.best_bid:.2f}  ask={m.best_ask:.2f}  "
        f"spread={m.spread:.2f}({m.spread_bps:.2f}bps)  "
        f"mid={m.mid_price:.2f}  wMid={m.weighted_mid:.2f}({pressure})  "
        f"OBI={m.obi:.3f}({obi_label})  "
        f"bidD={m.bid_depth:.3f}  askD={m.ask_depth:.3f}"
    )


# ─────────────────────────────────────────────
# REST 快照
# ─────────────────────────────────────────────

def fetch_snapshot() -> dict:
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None
    resp = requests.get(SNAPSHOT_URL, proxies=proxies, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────
# 订单簿重建主流程
# ─────────────────────────────────────────────

def run() -> None:
    ob = LocalOrderBook()
    msg_queue: queue.Queue = queue.Queue()
    initialized = False
    last_u: int = 0

    # 解析代理给 websocket-client
    ws_proxy_kwargs: dict = {}
    if PROXY:
        # 格式 socks5h://host:port 或 socks5://host:port
        from urllib.parse import urlparse
        parsed = urlparse(PROXY)
        ws_proxy_kwargs = {
            "proxy_type": "socks5",
            "http_proxy_host": parsed.hostname,
            "http_proxy_port": parsed.port,
        }

    def on_message(ws_app, message):
        msg_queue.put(json.loads(message))

    def on_error(ws_app, error):
        print(f"WS 错误: {error}")

    def on_open(ws_app):
        print("WebSocket 已连接")

    ws_app = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
    )

    # 在后台线程运行 WebSocket
    ws_thread = threading.Thread(
        target=ws_app.run_forever,
        kwargs=ws_proxy_kwargs,
        daemon=True,
    )
    ws_thread.start()

    # 等待 WS 连接建立，开始缓存消息
    print(f"连接 WebSocket: {WS_URL}")
    time.sleep(1)

    # Step 1: 拉取 REST 快照
    print("拉取订单簿快照...")
    snapshot = fetch_snapshot()
    ob.apply_snapshot(snapshot)
    snap_id = ob.last_update_id
    print(f"快照完毕，lastUpdateId={snap_id}，bids={len(ob.bids)}档，asks={len(ob.asks)}档")

    # Step 2: 处理队列中已缓存的消息，对齐版本号
    buffer = []
    while not msg_queue.empty():
        buffer.append(msg_queue.get_nowait())

    # 丢弃 u <= snap_id 的消息
    buffer = [m for m in buffer if m["u"] > snap_id]

    # 找第一条 U <= snap_id+1 <= u
    for msg in buffer:
        if msg["U"] <= snap_id + 1 <= msg["u"]:
            ob.apply_update(msg["b"], msg["a"], msg["u"])
            last_u = msg["u"]
            initialized = True
            break

    if not initialized:
        print("等待对齐消息...")

    # Step 3: 主循环持续消费队列
    while True:
        try:
            msg = msg_queue.get(timeout=5)
        except queue.Empty:
            print("5秒无消息，检查连接...")
            continue

        if not initialized:
            if msg["U"] <= snap_id + 1 <= msg["u"]:
                initialized = True
            else:
                continue

        # 验证版本连续性
        if last_u != 0 and msg["pu"] != last_u:
            print(f"版本号不连续 pu={msg['pu']} != last_u={last_u}，重新初始化...")
            return

        ob.apply_update(msg["b"], msg["a"], msg["u"])
        last_u = msg["u"]

        metrics = compute_metrics(ob)
        if metrics:
            print_metrics(metrics)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n已停止")