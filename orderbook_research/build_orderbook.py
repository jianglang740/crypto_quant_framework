'''
在测试脚本时会反复运行代码，直接使用主网的rest和ws地址容易导致IP被风控，我在测试脚本时就出现了这样的问题，踩坑后我改用了测试网地址，
建议在测试时使用测试网的rest和ws地址，且主网和测试网的地址容易搞混，我找到了如下所示的地址，方便调试：

1.基础主网rest接口：https://fapi.binance.com   btcusdt主网示例rest接口：https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000
2.基础主网ws接口：wss://fstream.binance.com    btcusdt主网示例ws接口：wss://fstream.binance.com/ws/btcusdt@depth

3.基础测试网rest接口：https://testnet.binancefuture.com     btcusdt测试网示例rest接口：https://testnet.binancefuture.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000
4.基础测试网ws接口：wss://stream.binancefuture.com          btcusdt测试网示例ws接口：wss://stream.binancefuture.com/ws/btcusdt@depth

且我一开始出现了一个问题，搞了好久才解决，我在本地调试时使用ssh代理来访问数据，但源码中我直接硬编码了 "proxy_type": "socks5"，
但socks5 模式：DNS 域名解析由代理服务器执行，socks5h 模式：DNS 域名解析由本地客户端执行，导致DNS无法解析公网域名，进而导致我在测试时虽然ws连接成功，但无法正常接收数据。

原写法是硬编码"proxy_type": "socks5"
我改成了proxy_type = "socks5h" if parsed.scheme == "socks5h" else "socks5"，"proxy_type": proxy_type
这样就能让 DNS 解析在本地执行，避免代理服务器解析失败的问题。
'''

import json
import queue 
import threading # 用于 WebSocket 消息的线程安全队列
import time
from dataclasses import dataclass, field

import requests
import websocket 
import decimal

SYMBOL = "btcusdt"
SYMBOL_UPPER = SYMBOL.upper()
DEPTH_LEVELS = 5  # 用于计算流动性指标时考虑的档位数量
# 测试网rest地址
SNAPSHOT_URL = f"https://testnet.binancefuture.com/fapi/v1/depth?symbol={SYMBOL_UPPER}&limit=1000"#全量快照接口
# 测试网ws地址
WS_URL = f"wss://stream.binancefuture.com/ws/{SYMBOL}@depth" #增量更新接口，默认100档深度更新（测试网WS端点不同）


#我的ssh云服务器代理
PROXY = "socks5h://127.0.0.1:1080"  

DEBUG = True  # 开启调试日志

# 本地订单簿数据结构，支持快照和增量更新的应用

class LocalOrderBook:
    def __init__(self) -> None:
        self.bids: dict[str, decimal.Decimal] = {} #用字典存储bids数据
        self.asks: dict[str, decimal.Decimal] = {} #用字典存储asks数据
        self.last_update_id: int = 0 #记录最后一次更新的版本号

    def apply_snapshot(self, snapshot: dict) -> None: #申请快照数据，初始化订单簿
        self.bids = {p: decimal.Decimal(q) for p, q in snapshot["bids"]} #将快照中的bids数据转换为decimal.Decimal类型并存储在字典中
        self.asks = {p: decimal.Decimal(q) for p, q in snapshot["asks"]} #同理将快照中的asks数据转换为decimal.Decimal类型并存储在字典中 
        self.last_update_id = snapshot["lastUpdateId"] #记录快照的版本号

    def apply_update(self, bids_diff: list, asks_diff: list, update_id: int) -> None: #应用增量更新数据，更新订单簿
        self._apply_side(self.bids, bids_diff) #申请方向为bids，数据类型为增量数据
        self._apply_side(self.asks, asks_diff) #申请方向为asks，数据类型为增量数据
        self.last_update_id = update_id

    @staticmethod #@staticmethod 是一个装饰器，让类里的方法不需要实例化对象、不需要 self，就能直接调用
    def _apply_side(side: dict[str, decimal.Decimal], diff: list) -> None:
        for price_str, qty_str in diff: #遍历交易所发送的增量更新数据
            qty = decimal.Decimal(qty_str)
            if qty == 0:
                side.pop(price_str, None) #如果数量为0，说明该档位被撤销了，从订单簿中删除对应的价格档位
            else:
                side[price_str] = qty #如果数量不为0，说明该档位被更新了，直接覆盖订单簿中对应价格档位的数量

    def sorted_bids(self) -> list[tuple[decimal.Decimal, decimal.Decimal]]: #返回排序后的bids数据，按照价格从高到低排序
        return sorted(((decimal.Decimal(p), q) for p, q in self.bids.items()), reverse=True)

    def sorted_asks(self) -> list[tuple[decimal.Decimal, decimal.Decimal]]: #返回排序后的asks数据，按照价格从低到高排序
        return sorted(((decimal.Decimal(p), q) for p, q in self.asks.items()), reverse=False)



# 流动性指标


@dataclass
class LiquidityMetrics:
    best_bid: decimal.Decimal #最优买价
    best_ask: decimal.Decimal #最优卖价
    spread: decimal.Decimal #二者价差
    spread_bps: decimal.Decimal #价差占中间价的基点数
    mid_price: decimal.Decimal #中间价
    weighted_mid: decimal.Decimal #加权中间价，考虑了最优档位的数量
    bid_depth: decimal.Decimal #买盘深度，前N档的数量总和
    ask_depth: decimal.Decimal #卖盘深度，前N档的数量总和
    obi: decimal.Decimal #订单簿不平衡度，计算公式为 bid_depth / (bid_depth + ask_depth)，范围在0到1之间，越接近1表示买盘越强，越接近0表示卖盘越强
    timestamp: float = field(default_factory=time.time) #指标计算的时间戳，默认为当前时间


def compute_metrics(ob: LocalOrderBook, levels: int = DEPTH_LEVELS) -> LiquidityMetrics | None: #计算流动性指标，参数为订单簿对象和考虑的档位数量，返回一个 LiquidityMetrics 对象或者 None（如果订单簿没有数据）
    bids = ob.sorted_bids() #获取排序后的bids数据
    asks = ob.sorted_asks() #获取排序后的asks数据
    if not bids or not asks:
        return None

    best_bid_p, best_bid_q = bids[0] #最优买价和数量，即bids中价格最高的档位
    best_ask_p, best_ask_q = asks[0] #最优卖价和数量，即asks中价格最低的档位
    spread = best_ask_p - best_bid_p #价差，等于最优卖价减去最优买价
    mid = (best_bid_p + best_ask_p) / 2 #中间价，等于最优买价和最优卖价的平均值
    weighted_mid = (best_bid_p * best_ask_q + best_ask_p * best_bid_q) / (best_bid_q + best_ask_q) #加权中间价，考虑了最优档位的数量，计算公式为 (best_bid_p * best_ask_q + best_ask_p * best_bid_q) / (best_bid_q + best_ask_q)，即用最优买价乘以最优卖量加上最优卖价乘以最优买量，再除以两者数量之和
    bid_depth = sum(q for _, q in bids[:levels]) #买盘深度，前N档的数量总和，使用列表切片 bids[:levels] 获取前N档数据，然后用生成器表达式 sum(q for _, q in ...) 计算数量的总和
    ask_depth = sum(q for _, q in asks[:levels]) #卖盘深度，前N档的数量总和，使用列表切片 asks[:levels] 获取前N档数据，然后用生成器表达式 sum(q for _, q in ...) 计算数量的总和
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
    ) #返回计算好的流动性指标对象，包含最优买价、最优卖价、价差、价差占中间价的基点数、中间价、加权中间价、买盘深度、卖盘深度和订单簿不平衡度


def print_metrics(m: LiquidityMetrics) -> None: #打印流动性指标，参数为一个 LiquidityMetrics 对象
    pressure = "买压" if m.weighted_mid < m.mid_price else "卖压" #根据加权中间价和中间价的关系判断买卖压力，如果加权中间价小于中间价，说明买压较大，反之则说明卖压较大
    obi_label = "买强" if m.obi > 0.6 else ("卖强" if m.obi < 0.4 else "均衡") #根据订单簿不平衡度的值判断买卖强弱，如果大于0.6，说明买盘较强，反之如果小于0.4，说明卖盘较强，否则认为买卖均衡
    print(
        f"bid={m.best_bid:.2f}  ask={m.best_ask:.2f}  "
        f"spread={m.spread:.2f}({m.spread_bps:.2f}bps)  "
        f"mid={m.mid_price:.2f}  wMid={m.weighted_mid:.2f}({pressure})  "
        f"OBI={m.obi:.3f}({obi_label})  "
        f"bidD={m.bid_depth:.3f}  askD={m.ask_depth:.3f}"
    ) #格式化输出流动性指标，显示最优买价、最优卖价、价差、价差占中间价的基点数、中间价、加权中间价和压力判断、订单簿不平衡度和强弱判断，以及买盘深度和卖盘深度



# REST 快照


def fetch_snapshot() -> dict: #从交易所拉取订单簿快照数据，返回一个字典对象，包含bids、asks和lastUpdateId等信息
    proxies = {"http": PROXY, "https": PROXY} if PROXY else None #如果设置了代理，则构造一个包含http和https代理的字典，否则为None
    resp = requests.get(SNAPSHOT_URL, proxies=proxies, timeout=15) #发送HTTP GET请求到快照接口，使用代理（如果有）和设置超时时间为15秒
    resp.raise_for_status() #如果响应状态码不是200，会抛出一个HTTPError异常
    return resp.json() #返回响应的JSON内容，应该是一个包含订单簿快照数据的字典对象


# 订单簿重建主流程


def run() -> None:
    ob = LocalOrderBook() #创建一个本地订单簿对象，用于存储和更新订单簿数据
    msg_queue: queue.Queue = queue.Queue() #创建一个线程安全的消息队列，用于在WebSocket线程和主线程之间传递增量更新消息
    initialized = False #一个标志变量，表示订单簿是否已经通过快照和增量消息对齐完成，初始值为False
    last_u: int = 0 #记录最后一次应用的增量消息的版本号，初始值为0

    # 解析代理给 websocket-client
    ws_proxy_kwargs: dict = {} #一个字典，用于存储WebSocket连接的代理参数，初始为空，如果设置了代理，会在下面填充相应的参数
    if PROXY:
        # 格式 socks5h://host:port 或 socks5://host:port
        from urllib.parse import urlparse #导入urlparse函数，用于解析代理URL
        parsed = urlparse(PROXY)
        # websocket-client 的 SOCKS5 代理参数
        # socks5h 表示 DNS 解析在客户端（本地），socks5 表示 DNS 解析在代理端
        proxy_type = "socks5h" if parsed.scheme == "socks5h" else "socks5"
        ws_proxy_kwargs = {
            "proxy_type": proxy_type,
            "http_proxy_host": parsed.hostname,
            "http_proxy_port": parsed.port,
        }
        print(f"使用代理: {proxy_type}://{parsed.hostname}:{parsed.port}")

    def on_message(ws_app, message): #WebSocket消息处理函数，当收到增量更新消息时被调用，参数为WebSocket应用对象和消息内容
        parsed = json.loads(message)
        if DEBUG:
            print(f"收到消息: U={parsed.get('U')}, u={parsed.get('u')}, pu={parsed.get('pu')}")
        msg_queue.put(parsed)

    def on_error(ws_app, error): #WebSocket错误处理函数，当WebSocket连接发生错误时被调用，参数为WebSocket应用对象和错误信息
        print(f"WS 错误: {error}")

    def on_open(ws_app): #WebSocket连接建立成功后的处理函数，当WebSocket连接成功建立时被调用，参数为WebSocket应用对象
        print("WebSocket 已连接")

    def on_close(ws_app, close_status_code, close_msg): #WebSocket连接关闭处理函数
        print(f"WS 连接关闭: code={close_status_code}, msg={close_msg}")

    ws_app = websocket.WebSocketApp( #创建一个WebSocket应用对象，参数包括连接URL和事件处理函数
        WS_URL,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
        on_close=on_close,
    )

    # 在后台线程运行 WebSocket
    ws_proxy_kwargs['ping_interval'] = 30  # 每30秒发送ping
    ws_proxy_kwargs['ping_timeout'] = 10   # ping超时10秒
    ws_thread = threading.Thread( #创建一个线程对象，参数包括目标函数、函数参数和是否为守护线程
        target=ws_app.run_forever, #目标函数是WebSocket应用对象的run_forever方法，用于持续运行WebSocket连接，函数参数包括ping_interval=30（每30秒发送一次ping消息保持连接活跃）和proxy参数（如果设置了代理，则传递相应的代理参数）
        kwargs=ws_proxy_kwargs, #传递WebSocket连接的代理参数，如果没有设置代理，则传递一个空字典
        daemon=True, #设置为守护线程，这样当主线程退出时，WebSocket线程也会自动退出
    )
    ws_thread.start() #启动WebSocket线程，开始连接交易所并接收增量更新消息

    # 等待 WS 连接建立，开始缓存消息
    print(f"连接 WebSocket: {WS_URL}") #输出连接WebSocket的URL信息，提示用户正在连接交易所的WebSocket接口
    time.sleep(1) #等待1秒钟，给WebSocket连接一些时间来建立连接和开始接收消息，这样在后续步骤中就可以从消息队列中获取到增量更新消息了

    # Step 1: 拉取 REST 快照
    print("拉取订单簿快照...")
    snapshot = fetch_snapshot()
    ob.apply_snapshot(snapshot)
    snap_id = ob.last_update_id
    print(f"快照完毕，lastUpdateId={snap_id}，bids={len(ob.bids)}档，asks={len(ob.asks)}档")

    # Step 2: 处理队列中已缓存的消息，对齐版本号
    buffer = [] #一个临时列表，用于存储从消息队列中获取的增量更新消息，初始为空
    while not msg_queue.empty(): #当消息队列不为空时，持续从队列中获取消息并存储在buffer列表中，直到队列为空为止
        buffer.append(msg_queue.get_nowait()) #从消息队列中获取一个消息，使用get_nowait方法，如果队列为空会抛出queue.Empty异常，这里不处理异常，因为循环条件已经检查了队列是否为空

    if DEBUG:
        print(f"缓存消息数: {len(buffer)}")
    
    # 丢弃 u <= snap_id 的消息
    buffer = [m for m in buffer if m["u"] > snap_id] #使用列表推导式过滤掉那些版本号u小于等于快照版本号snap_id的消息，因为这些消息已经过时了，不需要应用到订单簿上了
    
    if DEBUG:
        print(f"过滤后消息数: {len(buffer)}, snap_id={snap_id}")
        for i, msg in enumerate(buffer[:5]):
            print(f"  消息{i}: U={msg['U']}, u={msg['u']}")

    # 找第一条 U <= snap_id+1 <= u
    for msg in buffer: #遍历过滤后的消息列表，寻找第一条满足版本号连续性的消息，即U小于等于snap_id+1且u大于等于snap_id+1的消息，这样就可以确保从快照版本号开始，增量更新消息的版本号是连续的了
        if msg["U"] <= snap_id + 1 <= msg["u"]: #如果找到了满足条件的消息，就应用这条消息的增量更新数据到订单簿上，更新订单簿的版本号为这条消息的u，然后将last_u变量更新为这条消息的u，并将initialized标志设置为True，表示订单簿已经初始化完成了，最后跳出循环
            if DEBUG:
                print(f"找到对齐消息: U={msg['U']}, u={msg['u']}, snap_id+1={snap_id+1}")
            ob.apply_update(msg["b"], msg["a"], msg["u"]) #应用这条消息的增量更新数据到订单簿上，参数包括bids_diff、asks_diff和update_id，分别对应消息中的b、a和u字段
            last_u = msg["u"] #将last_u变量更新为这条消息的u字段，记录最后一次应用的增量消息的版本号
            initialized = True #将initialized标志设置为True，表示订单簿已经初始化完成了，可以开始应用后续的增量更新消息了
            break #跳出循环，不再继续寻找其他满足条件的消息了，因为已经找到了第一条满足条件的消息了

    if not initialized:
        print(f"等待对齐消息... 需要 U <= {snap_id+1} <= u")

    # Step 3: 主循环持续消费队列
    while True:
        try:
            msg = msg_queue.get(timeout=5)
        except queue.Empty:
            print("5秒无消息，检查连接...")
            continue

        if not initialized:
            if msg["U"] <= snap_id + 1 <= msg["u"]: #如果订单簿还没有初始化完成，继续寻找第一条满足版本号连续性的消息，即U小于等于snap_id+1且u大于等于snap_id+1的消息，这样就可以确保从快照版本号开始，增量更新消息的版本号是连续的了
                initialized = True #如果找到了满足条件的消息，就将initialized标志设置为True，表示订单簿已经初始化完成了，可以开始应用后续的增量更新消息了
            else:
                continue #如果当前消息不满足版本号连续性的条件，就继续等待下一条消息了，直到找到满足条件的消息为止

        # 验证版本连续性
        if last_u != 0 and msg["pu"] != last_u: #如果订单簿已经应用过增量消息了，那么就需要验证当前消息的版本号pu是否等于last_u，如果不相等，说明版本号不连续了，可能是丢包了或者消息乱序了，这时候需要重新初始化订单簿了，所以输出一个提示信息，并返回到主流程的开头，重新拉取快照和对齐增量消息
            print(f"版本号不连续 pu={msg['pu']} != last_u={last_u}，重新初始化...")
            return

        ob.apply_update(msg["b"], msg["a"], msg["u"]) #应用当前消息的增量更新数据到订单簿上，参数包括bids_diff、asks_diff和update_id，分别对应消息中的b、a和u字段
        last_u = msg["u"] #将last_u变量更新为当前消息的u字段，记录最后一次应用的增量消息的版本号

        metrics = compute_metrics(ob) #计算当前订单簿的流动性指标，参数为订单簿对象ob，返回一个LiquidityMetrics对象或者None（如果订单簿没有数据）
        if metrics: #如果成功计算出了流动性指标，就调用print_metrics函数打印这些指标，参数为计算得到的LiquidityMetrics对象
            print_metrics(metrics) #调用print_metrics函数打印流动性指标，参数为计算得到的LiquidityMetrics对象


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n已停止")