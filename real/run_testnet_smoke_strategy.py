# !!!!这不算事一个真正的量化策略，只是一个基于while循环的简单马丁策略测试脚本，主要目的不是赚钱，是验证框架稳定性


import json #把 Python 的字典、列表等数据结构，转换成 JSON 格式的字符串，方便存储到文件或网络传输，主要是把 Python dict 转成字符串，存进数据库
import os
import sys #主要用于操作 Python 的模块搜索路径
import time #用于控制时间，本脚本中用于暂停程序
from datetime import datetime, timezone#分别表示时间日期和时区
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

'''
#__file__是 Python 自动提供的变量，表示“当前这个 Python 文件的路径”
Path(__file__)把__file__这个路径字符串变成一个Path对象
.resolve()作用是把路径解析成绝对路径
.parents[n]表示与父级目录的关系,n从0开始取值,例如n=1,就退回到上两级父级目录所在的路径
'''

PROJECT_ROOT = Path(__file__).resolve().parents[1]  #把当前脚本所在项目的根目录找出来
if str(PROJECT_ROOT) not in sys.path: #Python会在sys.path里的目录中，一个个找你所导入的类，如果找不到，就会报ModuleNotFoundError: No module named '你导入的类所在的文件夹'
    sys.path.insert(0, str(PROJECT_ROOT)) #把项目路径转换成字符串并加入sys.path
'''
找到当前脚本所在项目的根目录；
如果这个根目录还不在 Python 模块搜索路径里；
就把它插到搜索路径最前面；
这样后面就可以稳定导入项目内部的 crypto_quant 包
'''

from crypto_quant.config import ExchangeConfig, MySQLConfig
from crypto_quant.database import TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.database.models import TradeRecord
from crypto_quant.enums import OrderSide, OrderType, PositionSide, TradingMode
from crypto_quant.exchange import ExchangeClient, ExchangeClientError
from crypto_quant.strategy.base import Account, Position, StrategyBase

#全局变量
SYMBOL = os.getenv("CRYPTO_QUANT_TESTNET_SYMBOL") or os.getenv("TESTNET_SYMBOL", "BTC/USDT")
BASE_ASSET = os.getenv("CRYPTO_QUANT_TESTNET_BASE_ASSET") or os.getenv("TESTNET_BASE_ASSET", SYMBOL.split("/")[0]) #得到的结果是“BTC”，基础资产
QUOTE_ASSET = os.getenv("CRYPTO_QUANT_TESTNET_QUOTE_ASSET") or os.getenv("TESTNET_QUOTE_ASSET", SYMBOL.split("/")[1]) #得到的结果是“USDT”，计价资产
#当前策略参数
TIMEFRAME = "5m"
TRADE_NOTIONAL_USDT = Decimal("20") #每次使用20usdt交易
TRADE_BASE_AMOUNT = Decimal("0.1") #每次买入0.1btc
MARTINGALE_MULTIPLIER = Decimal("1") #补仓倍数
MARTINGALE_MAX_STEPS = 4 #最多补仓层数
MARTINGALE_DROP_PCT = Decimal("0.005") #每下跌0.5%进行一次补仓判断
MARTINGALE_TAKE_PROFIT_PCT = Decimal("0.002") #相对于平均入场价上涨0.2%止盈
SNAPSHOT_INTERVAL_SECONDS = 30 #每轮循环之间等待30s
MAX_CYCLES = 0 #0表示无限循环
RUN_ID = os.getenv("CRYPTO_QUANT_TESTNET_RUN_ID") or os.getenv("TESTNET_RUN_ID") or f"testnet_smoke_{datetime.now():%Y%m%d_%H%M%S}" #给本次测试网运行生成一个唯一 ID，用于写入数据表
ORDER_FETCH_RETRIES = int(os.getenv("CRYPTO_QUANT_TESTNET_ORDER_FETCH_RETRIES") or os.getenv("TESTNET_ORDER_FETCH_RETRIES", "5"))
ORDER_FETCH_RETRY_DELAY_SECONDS = float(os.getenv("CRYPTO_QUANT_TESTNET_ORDER_FETCH_RETRY_DELAY_SECONDS") or os.getenv("TESTNET_ORDER_FETCH_RETRY_DELAY_SECONDS", "2"))

'''
下单后，交易所不一定立刻能通过 fetch_order / fetch_order_trades 查到订单和成交。
所以这里允许重试。
最多重试 5 次
每次间隔 2 秒
'''

class TestnetSmokeStrategy(StrategyBase):
    name = "testnet_martingale_strategy"

#从环境变量读取 MySQL 连接配置
def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT") or os.getenv("MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME") or os.getenv("MYSQL_USER", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", "crypto_quant"),
    )

#从环境变量读取 OKX Demo 的 API key、secret 和 passphrase
def okx_config_from_env() -> ExchangeConfig:
    proxies = None
    proxy_url = os.getenv("CRYPTO_QUANT_OKX_PROXY_URL") or os.getenv("OKX_PROXY_URL")
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
        ''' 
        优先读 CRYPTO_QUANT_OKX_DEMO_API_KEY 
        如果没有，就必须有 OKX_DEMO_API_KEY
        如果两个都没有，就报错
        '''
    return ExchangeConfig(
        api_key=os.getenv("CRYPTO_QUANT_OKX_DEMO_API_KEY") or os.environ["OKX_DEMO_API_KEY"],
        secret=os.getenv("CRYPTO_QUANT_OKX_DEMO_SECRET_KEY") or os.environ["OKX_DEMO_SECRET_KEY"],
        password=os.getenv("CRYPTO_QUANT_OKX_DEMO_PASSPHRASE") or os.environ["OKX_DEMO_PASSPHRASE"],
        trading_mode=TradingMode.SPOT,
        sandbox=True,
        proxies=proxies,
    )

#把交易所返回的数字统一转成 Decimal
def decimal_from_value(value) -> Decimal:
    return Decimal(str(value or "0"))

'''
ccxt 返回的余额通常类似：
{
    "free": {"BTC": 0.1, "USDT": 1000},
    "total": {"BTC": 0.1, "USDT": 1000},
}
这个函数用于提取：
free.BTC
free.USDT
total.USDT
'''

def decimal_from_balance(balance: dict, group: str, asset: str) -> Decimal:
    return Decimal(str(balance.get(group, {}).get(asset, 0)))

#把交易所返回的毫秒时间戳转换成 Python datetime
def datetime_from_milliseconds(value) -> datetime:
    if value is None:
        return datetime.utcnow()
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None) #转换成datetime日期

#从 OKX Demo 拉取当前最新价格
'''
它使用的是 ticker,不是 K 线。
所以这个脚本的交易判断是基于当前价格快照，而不是基于完整历史 K 线序列
'''
def latest_price(client: ExchangeClient) -> Decimal:
    ticker = client.exchange.fetch_ticker(SYMBOL)
    return decimal_from_value(ticker.get("last") or ticker.get("close"))

#给交易所返回的 trade 生成一个唯一 key，避免重复入库
'''
优先使用交易所成交 ID
如果没有成交 ID,就用订单号、时间、方向、数量、价格拼成一个 JSON key
'''
def trade_key(trade: dict) -> str:
    trade_id = trade.get("id")
    if trade_id is not None:
        return f"trade:{trade_id}"
    return json.dumps(
        {
            "order": trade.get("order"),
            "timestamp": trade.get("timestamp"),
            "side": trade.get("side"),
            "amount": trade.get("amount"),
            "price": trade.get("price"),
        },
        sort_keys=True,
        default=str,
    )

#把 ccxt 返回的成交 dict 转换成项目数据库模型 TradeRecord
def trade_record_from_ccxt(
    trade: dict,
    run_id: str,
    strategy_name: str,
    realized_pnl: Decimal | None = None,
) -> TradeRecord:
    fee = trade.get("fee") or {}
    return TradeRecord(
        run_id=run_id,
        strategy_name=strategy_name,
        exchange="okx_demo",
        exchange_trade_id=str(trade.get("id")) if trade.get("id") is not None else None,
        exchange_order_id=str(trade.get("order")) if trade.get("order") is not None else None,
        trading_mode=TradingMode.SPOT.value,
        symbol=trade["symbol"],
        side=trade["side"],
        position_side=PositionSide.BOTH.value,
        amount=decimal_from_value(trade.get("amount")),
        price=decimal_from_value(trade.get("price")),
        fee=decimal_from_value(fee.get("cost")),
        fee_asset=fee.get("currency"),
        realized_pnl=realized_pnl,
        traded_at=datetime_from_milliseconds(trade.get("timestamp")),
        raw=json.dumps(trade, ensure_ascii=False, default=str),
    )

#同步账户和持仓
'''
1. 从 OKX Demo 读取账户余额；
2. 提取 BASE_ASSET 和 QUOTE_ASSET；
3. 用最新价格估算基础资产市值；
4. 更新 strategy.account；
5. 如果持有基础资产，则更新 strategy.positions；
6. 如果没有持仓，则清空 strategy.positions；
7. 返回原始 balance。
'''
def sync_account_and_position(
    strategy: StrategyBase,
    client: ExchangeClient,
    mark_price: Decimal,
    entry_price: Decimal | None,
    raw_balance: dict | None = None,
) -> dict:
    balance = raw_balance or client.fetch_balance()
    base_free = decimal_from_balance(balance, "free", BASE_ASSET)
    quote_free = decimal_from_balance(balance, "free", QUOTE_ASSET)
    quote_total = decimal_from_balance(balance, "total", QUOTE_ASSET)
    position_value = base_free * mark_price
    unrealized_pnl = Decimal("0") if entry_price is None else (mark_price - entry_price) * base_free

    strategy.account = Account(
        cash=quote_total,
        equity=quote_total + position_value,
        available=quote_free,
        unrealized_pnl=unrealized_pnl,
    )
    if base_free > Decimal("0"):
        strategy.positions = {
            f"{SYMBOL}:{PositionSide.BOTH.value}": Position(
                symbol=SYMBOL,
                side=PositionSide.BOTH,
                amount=base_free,
                entry_price=entry_price or mark_price,
                mark_price=mark_price,
                unrealized_pnl=unrealized_pnl,
            )
        }
    else:
        strategy.positions = {}
    return balance

#订单和成交保存函数
def save_order_once(
    repository: TradingRepository,
    seen_order_ids: set[str],
    order: dict,
    run_id: str,
    strategy_name: str,
) -> None:
    order_id = str(order.get("id") or order.get("clientOrderId"))
    if not order_id or order_id in seen_order_ids:
        return
    repository.save_order(order, trading_mode=TradingMode.SPOT.value, run_id=run_id, strategy_name=strategy_name)
    seen_order_ids.add(order_id)

#下单后再次从交易所查询订单状态，并更新数据库里的订单状态、成交数量和均价
def update_order_from_exchange(repository: TradingRepository, order: dict, run_id: str) -> None:
    order_id = str(order.get("id") or order.get("clientOrderId"))
    repository.update_order_status(
        order_id,
        order.get("status", "open"),
        run_id=run_id,
        filled=decimal_from_value(order.get("filled")),
        average=Decimal(str(order["average"])) if order.get("average") is not None else None,
    )

#把成交明细保存到 trades 表，并通过 seen_trade_ids 防止重复保存
def save_trades_once(
    repository: TradingRepository,
    seen_trade_ids: set[str],
    trades: list[dict],
    run_id: str,
    strategy_name: str,
    realized_pnl: Decimal | None = None,
) -> int:
    saved_count = 0
    for trade in trades:
        key = trade_key(trade)
        if key in seen_trade_ids:
            continue
        repository.save_trade(trade_record_from_ccxt(trade, run_id, strategy_name, realized_pnl=realized_pnl))
        seen_trade_ids.add(key)
        saved_count += 1
    return saved_count

#把当前账户、持仓和权益点写入数据库
def record_snapshot(repository: TradingRepository, strategy: StrategyBase, run_id: str) -> None:
    timestamp = datetime.utcnow()
    repository.save_live_snapshot(strategy, run_id, timestamp=timestamp)
    repository.save_equity_point(
        timestamp=timestamp,
        account=strategy.account,
        strategy_name=strategy.name,
        run_id=run_id,
        trading_mode=strategy.trading_mode.value,
    )

#向 OKX Demo 发送市价单
def create_market_order(client: ExchangeClient, side: OrderSide, amount: Decimal) -> dict:
    return client.create_order(
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.MARKET,
        amount=float(amount),
    )

#根据当前价格、可用 USDT、补仓步数，计算本次可以买多少 BTC
def buy_amount_from_balance(price: Decimal, quote_free: Decimal, step: int) -> Decimal:
    multiplier = MARTINGALE_MULTIPLIER ** step
    if TRADE_BASE_AMOUNT is not None:
        amount = TRADE_BASE_AMOUNT * multiplier
        if quote_free < amount * price:
            return Decimal("0")
        return amount
    notional = TRADE_NOTIONAL_USDT * multiplier
    if quote_free < notional:
        return Decimal("0")
    return notional / price


#补仓后重新计算平均入场价
def weighted_entry_price(current_amount: Decimal, current_entry: Decimal | None, fill_amount: Decimal, fill_price: Decimal) -> Decimal:
    if current_amount <= Decimal("0") or current_entry is None:
        return fill_price
    total_amount = current_amount + fill_amount
    if total_amount <= Decimal("0"):
        return fill_price
    return ((current_entry * current_amount) + (fill_price * fill_amount)) / total_amount

#订单和成交查询重试
def fetch_order_with_retry(client: ExchangeClient, order_id: str) -> dict:
    last_error: ExchangeClientError | None = None
    for attempt in range(1, ORDER_FETCH_RETRIES + 1):
        try:
            return client.fetch_order(order_id, SYMBOL)
        except ExchangeClientError as exc:
            last_error = exc
            if "Order does not exist" not in str(exc) or attempt == ORDER_FETCH_RETRIES:
                raise
            print(f"[{datetime.now():%F %T}] order {order_id} not visible yet, retry {attempt}/{ORDER_FETCH_RETRIES}")
            time.sleep(ORDER_FETCH_RETRY_DELAY_SECONDS)
    raise last_error or ExchangeClientError(f"fetch_order failed: order {order_id} not found")

#下单后查询这张订单对应的成交明细
def fetch_order_trades_with_retry(client: ExchangeClient, order_id: str) -> list[dict]:
    for attempt in range(1, ORDER_FETCH_RETRIES + 1):
        trades = client.fetch_order_trades(order_id, SYMBOL)
        if trades or attempt == ORDER_FETCH_RETRIES:
            return trades
        print(f"[{datetime.now():%F %T}] order {order_id} trades not visible yet, retry {attempt}/{ORDER_FETCH_RETRIES}")
        time.sleep(ORDER_FETCH_RETRY_DELAY_SECONDS)
    return []


def main() -> None:
    client = ExchangeClient(okx_config_from_env())
    client.load_markets()

    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)

    strategy = TestnetSmokeStrategy(trading_mode=TradingMode.SPOT)
    seen_order_ids: set[str] = set()
    seen_trade_ids: set[str] = set()
    entry_price: Decimal | None = None
    last_buy_price: Decimal | None = None
    martingale_step = 0
    cycle = 0

    with Session() as session:
        repository = TradingRepository(session)
        price = latest_price(client)
        sync_account_and_position(strategy, client, price, entry_price)
        run = repository.create_run(
            run_id=RUN_ID,
            name="okx_demo_martingale_strategy",
            run_type="testnet",
            trading_mode=TradingMode.SPOT.value,
            strategy_name=strategy.name,
            symbols=[SYMBOL],
            timeframe=TIMEFRAME,
            initial_cash=strategy.account.equity,
            config={
                "source": "real/run_testnet_smoke_strategy.py",
                "exchange": "okx_demo",
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME,
                "sandbox": True,
                "trade_notional_usdt": str(TRADE_NOTIONAL_USDT),
                "trade_base_amount": str(TRADE_BASE_AMOUNT) if TRADE_BASE_AMOUNT is not None else None,
                "martingale_multiplier": str(MARTINGALE_MULTIPLIER),
                "martingale_max_steps": MARTINGALE_MAX_STEPS,
                "martingale_drop_pct": str(MARTINGALE_DROP_PCT),
                "martingale_take_profit_pct": str(MARTINGALE_TAKE_PROFIT_PCT),
                "snapshot_interval_seconds": SNAPSHOT_INTERVAL_SECONDS,
                "max_cycles": MAX_CYCLES,
            },
        )
        print(f"started testnet smoke run: run_id={run.run_id}, symbol={SYMBOL}")

        try:
            while MAX_CYCLES <= 0 or cycle < MAX_CYCLES:
                cycle += 1
                price = latest_price(client)
                balance = sync_account_and_position(strategy, client, price, entry_price)
                base_free = decimal_from_balance(balance, "free", BASE_ASSET)
                quote_free = decimal_from_balance(balance, "free", QUOTE_ASSET)

                if base_free <= Decimal("0"):
                    martingale_step = 0
                    buy_amount = buy_amount_from_balance(price, quote_free, martingale_step)
                    if buy_amount <= Decimal("0"):
                        print(f"[{datetime.now():%F %T}] insufficient {QUOTE_ASSET} balance for initial buy, free={quote_free}")
                        record_snapshot(repository, strategy, run.run_id)
                        time.sleep(SNAPSHOT_INTERVAL_SECONDS)
                        continue
                    order = create_market_order(client, OrderSide.BUY, buy_amount)
                    save_order_once(repository, seen_order_ids, order, run.run_id, strategy.name)
                    fetched_order = fetch_order_with_retry(client, str(order["id"]))
                    update_order_from_exchange(repository, fetched_order, run.run_id)
                    fill_amount = decimal_from_value(fetched_order.get("filled"))
                    fill_price = decimal_from_value(fetched_order.get("average")) or price
                    trades = fetch_order_trades_with_retry(client, str(order["id"]))
                    save_trades_once(repository, seen_trade_ids, trades, run.run_id, strategy.name)
                    entry_price = fill_price
                    last_buy_price = fill_price
                    print(f"[{datetime.now():%F %T}] initial buy step={martingale_step} filled={fill_amount} avg={fill_price}")
                elif base_free > Decimal("0"):
                    if entry_price is None:
                        entry_price = price
                        last_buy_price = price
                    take_profit_price = entry_price * (Decimal("1") + MARTINGALE_TAKE_PROFIT_PCT)
                    next_buy_price = (last_buy_price or entry_price) * (Decimal("1") - MARTINGALE_DROP_PCT)
                    if price >= take_profit_price:
                        sell_amount = base_free
                        order = create_market_order(client, OrderSide.SELL, sell_amount)
                        save_order_once(repository, seen_order_ids, order, run.run_id, strategy.name)
                        fetched_order = fetch_order_with_retry(client, str(order["id"]))
                        update_order_from_exchange(repository, fetched_order, run.run_id)
                        exit_price = decimal_from_value(fetched_order.get("average")) or price
                        filled_amount = decimal_from_value(fetched_order.get("filled"))
                        realized_pnl = (exit_price - entry_price) * filled_amount
                        trades = fetch_order_trades_with_retry(client, str(order["id"]))
                        save_trades_once(repository, seen_trade_ids, trades, run.run_id, strategy.name, realized_pnl=realized_pnl)
                        entry_price = None
                        last_buy_price = None
                        martingale_step = 0
                        print(f"[{datetime.now():%F %T}] take profit sell filled={filled_amount} avg={exit_price} pnl={realized_pnl}")
                    elif martingale_step < MARTINGALE_MAX_STEPS and price <= next_buy_price:
                        next_step = martingale_step + 1
                        buy_amount = buy_amount_from_balance(price, quote_free, next_step)
                        if buy_amount <= Decimal("0"):
                            print(f"[{datetime.now():%F %T}] insufficient {QUOTE_ASSET} balance for martingale step={next_step}, free={quote_free}")
                        else:
                            order = create_market_order(client, OrderSide.BUY, buy_amount)
                            save_order_once(repository, seen_order_ids, order, run.run_id, strategy.name)
                            fetched_order = fetch_order_with_retry(client, str(order["id"]))
                            update_order_from_exchange(repository, fetched_order, run.run_id)
                            fill_amount = decimal_from_value(fetched_order.get("filled"))
                            fill_price = decimal_from_value(fetched_order.get("average")) or price
                            trades = fetch_order_trades_with_retry(client, str(order["id"]))
                            save_trades_once(repository, seen_trade_ids, trades, run.run_id, strategy.name)
                            entry_price = weighted_entry_price(base_free, entry_price, fill_amount, fill_price)
                            last_buy_price = fill_price
                            martingale_step = next_step
                            print(f"[{datetime.now():%F %T}] martingale buy step={martingale_step} filled={fill_amount} avg={fill_price} entry={entry_price}")

                price = latest_price(client)
                sync_account_and_position(strategy, client, price, entry_price)
                record_snapshot(repository, strategy, run.run_id)
                print(f"[{datetime.now():%F %T}] snapshot cycle={cycle} equity={strategy.account.equity} positions={len(strategy.positions)}")
                time.sleep(SNAPSHOT_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="stopped")
            print(f"stopped testnet smoke run: run_id={run.run_id}")
            return
        except Exception:
            session.rollback()
            repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="failed")
            raise

        repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="finished")
        print(f"finished testnet smoke run: run_id={run.run_id}")


if __name__ == "__main__":
    main()
