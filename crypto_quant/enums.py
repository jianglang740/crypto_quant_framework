from enum import StrEnum #StrEnum 是 Python 的字符串枚举，意思是每个枚举值本质上也是字符串


class TradingMode(StrEnum): #交易模式枚举
    SPOT = "spot" #现货交易
    FUTURE = "future" #合约交易


class MarginMode(StrEnum): #保证金模式枚举
    CROSS = "cross" #全仓
    ISOLATED = "isolated" #逐仓

'''
PositionSide = 当前仓位方向
OrderSide = 这笔订单是买还是卖
'''

class PositionSide(StrEnum): #持仓方向枚举
    LONG = "long" #多头
    SHORT = "short" #空头
    BOTH = "BOTH" #框架内部普通持仓槽位（现货/单向持仓模式）


class OrderSide(StrEnum): #订单买卖方向枚举
    BUY = "buy" #在现货模式下表示买币，在合约模式下表示开多或平空
    SELL = "sell" #在现货模式下表示卖币，在合约模式下表示开空或平多


class OrderType(StrEnum): #订单类型枚举
    MARKET = "market" #市价单
    LIMIT = "limit" #限价单
    STOP = "stop" #止损限价单
    STOP_MARKET = "stop_market" #止损市价单
    TAKE_PROFIT = "take_profit" #止盈限价单
    TAKE_PROFIT_MARKET = "take_profit_market" #止盈市价单
    TRAILING_STOP_MARKET = "trailing_stop_market" #移动止损市价单


class TimeInForce(StrEnum): #限价单有效方式枚举
    GTC = "GTC" #订单一直有效，直到成交或你主动取消
    IOC = "IOC" #能立刻成交多少就成交多少，剩下没成交的马上取消
    FOK = "FOK" #要么全部立刻成交，要么全部取消
    GTX = "GTX" #只做 maker 挂单；如果这笔单会立刻吃单成交，就取消


class KlineInterval(StrEnum): #k线周期枚举
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    D3 = "3d"
    W1 = "1w"
    MN1 = "1M"


class OrderStatus(StrEnum): #订单状态枚举
    OPEN = "open" #开单中，订单已经提交，但还没有完全结束
    CLOSED = "closed" #订单已经成交完毕
    CANCELED = "canceled" #表示订单已取消
    EXPIRED = "expired" #表示订单过期，比如某些有有效期的订单，超过时间没有成交，就过期了
    REJECTED = "rejected" #表示订单被拒绝

'''
常见原因：

余额不足
数量太小
价格不合法
交易对不存在
风控限制
交易所拒绝
'''


class DataField(StrEnum): #k线字段枚举
    DATETIME = "datetime"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"
