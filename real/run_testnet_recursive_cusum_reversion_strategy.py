import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.config import BinanceConfig, MySQLConfig
from crypto_quant.data import BarData, DataFeed, MarketDataFetcher
from crypto_quant.database import TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.database.models import TradeRecord
from crypto_quant.enums import MarginMode, OrderSide, OrderStatus, OrderType, PositionSide, TradingMode
from crypto_quant.exchange import BinanceClient, BinanceClientError
from crypto_quant.strategy.base import Account, LocalOrder, OrderRequest, Position, StrategyBase


SYMBOL = "ETH/USDT"
BASE_ASSET = SYMBOL.split("/")[0]
QUOTE_ASSET = SYMBOL.split("/")[1]
TIMEFRAME = "5m"
EXCHANGE = "binance_testnet"

THRESHOLD = Decimal("0.07")
TAKE_PROFIT_RATE = Decimal("0.018")
STOP_LOSS_RATE = Decimal("0.033")
POSITION_RATIO = Decimal("0.30")
LEVERAGE = Decimal("10")
MARGIN_MODE = MarginMode.CROSS

KLINE_LIMIT = 500
SNAPSHOT_INTERVAL_SECONDS = 30
MAX_CYCLES = 0
RUN_ID = f"testnet_recursive_cusum_reversion_{datetime.now():%Y%m%d_%H%M%S}"
ORDER_FETCH_RETRIES = 5
ORDER_FETCH_RETRY_DELAY_SECONDS = 2


@dataclass(slots=True)
class TestnetExecutionConfig:
    leverage: Decimal


class RecursiveCusumReversionFuturesStrategy(StrategyBase):
    name = "testnet_recursive_cusum_reversion_futures"

    def __init__(
        self,
        threshold: Decimal = THRESHOLD,
        take_profit_rate: Decimal = TAKE_PROFIT_RATE,
        stop_loss_rate: Decimal = STOP_LOSS_RATE,
        position_ratio: Decimal = POSITION_RATIO,
    ):
        super().__init__(trading_mode=TradingMode.FUTURE)
        self.threshold = threshold
        self.take_profit_rate = take_profit_rate
        self.stop_loss_rate = stop_loss_rate
        self.position_ratio = position_ratio
        self.signals: list[int] = []

    def on_init(self) -> None:
        if self.data is None:
            return
        df = self.data.to_dataframe()
        close = df["close"].astype(float)
        log_return = np.log(close / close.shift(1)).fillna(0)
        threshold = float(self.threshold)
        signals = [0] * len(df)
        pos_sum = 0.0
        neg_sum = 0.0
        for i in range(1, len(df)):
            value = float(log_return.iloc[i])
            pos_sum = max(0.0, pos_sum + value)
            neg_sum = min(0.0, neg_sum + value)
            if pos_sum >= threshold:
                signals[i] = 1
                pos_sum = 0.0
                neg_sum = 0.0
            elif neg_sum <= -threshold:
                signals[i] = -1
                pos_sum = 0.0
                neg_sum = 0.0
        self.signals = signals

    def on_bar(self, bar: BarData) -> None:
        if self.data is None:
            return
        signal = self.signals[self.data.cursor] if self.data.cursor < len(self.signals) else 0

        if self._check_take_profit_stop_loss(bar):
            return

        if signal == 1:
            self._reverse_to_long(bar)
        elif signal == -1:
            self._reverse_to_short(bar)

    def on_stop(self) -> None:
        self.close_position(SYMBOL, PositionSide.BOTH)
        self.close_position(SYMBOL, PositionSide.SHORT)

    def _check_take_profit_stop_loss(self, bar: BarData) -> bool:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not long_position.is_flat and long_position.entry_price > 0:
            pnl_rate = bar.close / long_position.entry_price - Decimal("1")
            if pnl_rate >= self.take_profit_rate or pnl_rate <= -self.stop_loss_rate:
                self.close_position(bar.symbol, PositionSide.BOTH)
                return True
        if not short_position.is_flat and short_position.entry_price > 0:
            pnl_rate = short_position.entry_price / bar.close - Decimal("1")
            if pnl_rate >= self.take_profit_rate or pnl_rate <= -self.stop_loss_rate:
                self.cover(bar.symbol, abs(short_position.amount))
                return True
        return False

    def _reverse_to_long(self, bar: BarData) -> None:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not short_position.is_flat:
            self.cover(bar.symbol, abs(short_position.amount))
        if long_position.is_flat:
            self.buy(bar.symbol, self._order_amount(bar.close))

    def _reverse_to_short(self, bar: BarData) -> None:
        long_position = self.get_position(bar.symbol, PositionSide.BOTH)
        short_position = self.get_position(bar.symbol, PositionSide.SHORT)
        if not long_position.is_flat:
            self.close_position(bar.symbol, PositionSide.BOTH)
        if short_position.is_flat:
            self.short(bar.symbol, self._order_amount(bar.close))

    def _order_amount(self, price: Decimal) -> Decimal:
        leverage = self.engine.config.leverage if self.engine is not None else Decimal("1")
        amount = self.account.available * leverage * self.position_ratio / price
        return max(amount, Decimal("0"))


class TestnetOrderExecutionEngine:
    def __init__(self, client: BinanceClient, repository: TradingRepository, run_id: str):
        self.client = client
        self.repository = repository
        self.run_id = run_id
        self.config = TestnetExecutionConfig(leverage=LEVERAGE)
        self.seen_order_ids: set[str] = set()
        self.seen_trade_ids: set[str] = set()

    def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        if request.amount <= Decimal("0"):
            return self._record_rejected_order(strategy, request)
        exchange_position_side = self._exchange_position_side(request)
        order = self.client.create_order(
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            amount=float(request.amount),
            price=float(request.price) if request.price is not None else None,
            position_side=exchange_position_side,
            reduce_only=request.reduce_only,
            time_in_force=request.time_in_force.value if request.time_in_force else None,
            params=request.params,
        )
        self._save_order_once(order, strategy.name)
        fetched_order = fetch_order_with_retry(self.client, str(order["id"]))
        self._update_order_from_exchange(fetched_order)
        trades = fetch_order_trades_with_retry(self.client, str(order["id"]))
        self._save_trades_once(trades, strategy.name, request.position_side)
        self._record_local_order(strategy, request, fetched_order)
        sync_account_and_positions(strategy, self.client)
        return str(order.get("id") or order.get("clientOrderId") or uuid4())

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None:
        order = strategy.orders[order_id]
        result = self.client.cancel_order(order_id, order.request.symbol)
        order.status = OrderStatus.CANCELED if not isinstance(result, dict) else parse_order_status(result.get("status"))
        strategy.on_order(order)

    def _exchange_position_side(self, request: OrderRequest) -> PositionSide | None:
        if request.position_side == PositionSide.SHORT:
            return PositionSide.SHORT
        if request.position_side == PositionSide.BOTH or request.position_side is None:
            return PositionSide.LONG
        return request.position_side

    def _record_rejected_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        local_order = LocalOrder(id=f"rejected-{uuid4()}", request=request, status=OrderStatus.REJECTED)
        strategy.orders[local_order.id] = local_order
        strategy.on_order(local_order)
        return local_order.id

    def _record_local_order(self, strategy: StrategyBase, request: OrderRequest, order: dict) -> None:
        local_order = LocalOrder(
            id=str(order.get("id") or order.get("clientOrderId") or uuid4()),
            request=request,
            status=parse_order_status(order.get("status")),
            filled=decimal_from_value(order.get("filled")),
            average=optional_decimal(order.get("average")),
        )
        strategy.orders[local_order.id] = local_order
        strategy.on_order(local_order)

    def _save_order_once(self, order: dict, strategy_name: str) -> None:
        order_id = str(order.get("id") or order.get("clientOrderId"))
        if not order_id or order_id in self.seen_order_ids:
            return
        self.repository.save_order(order, trading_mode=TradingMode.FUTURE.value, run_id=self.run_id, strategy_name=strategy_name)
        self.seen_order_ids.add(order_id)

    def _update_order_from_exchange(self, order: dict) -> None:
        order_id = str(order.get("id") or order.get("clientOrderId"))
        self.repository.update_order_status(
            order_id,
            order.get("status", "open"),
            run_id=self.run_id,
            filled=decimal_from_value(order.get("filled")),
            average=optional_decimal(order.get("average")),
        )

    def _save_trades_once(self, trades: list[dict], strategy_name: str, position_side: PositionSide | None) -> None:
        for trade in trades:
            key = trade_key(trade)
            if key in self.seen_trade_ids:
                continue
            self.repository.save_trade(trade_record_from_ccxt(trade, self.run_id, strategy_name, position_side))
            self.seen_trade_ids.add(key)


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT") or os.getenv("MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME") or os.getenv("MYSQL_USER", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", "crypto_quant"),
    )


def binance_config_from_env() -> BinanceConfig:
    proxies = None
    proxy_url = os.getenv("CRYPTO_QUANT_BINANCE_PROXY_URL") or os.getenv("BINANCE_PROXY_URL")
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    return BinanceConfig(
        api_key=os.environ["CRYPTO_QUANT_BINANCE_FUTURES_TESTNET_API_KEY"],
        secret=os.environ["CRYPTO_QUANT_BINANCE_FUTURES_TESTNET_SECRET_KEY"],
        trading_mode=TradingMode.FUTURE,
        sandbox=True,
        proxies=proxies,
    )


def decimal_from_value(value) -> Decimal:
    return Decimal(str(value or "0"))


def optional_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def first_decimal(*values) -> Decimal:
    for value in values:
        if value not in (None, ""):
            return Decimal(str(value))
    return Decimal("0")


def datetime_from_milliseconds(value) -> datetime:
    if value is None:
        return datetime.utcnow()
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)


def parse_order_status(value) -> OrderStatus:
    normalized = str(value or OrderStatus.OPEN.value).lower()
    for status in OrderStatus:
        if normalized in {status.value.lower(), status.name.lower()}:
            return status
    return OrderStatus.OPEN


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


def trade_record_from_ccxt(
    trade: dict,
    run_id: str,
    strategy_name: str,
    position_side: PositionSide | None,
) -> TradeRecord:
    fee = trade.get("fee") or {}
    return TradeRecord(
        run_id=run_id,
        strategy_name=strategy_name,
        exchange=EXCHANGE,
        exchange_trade_id=str(trade.get("id")) if trade.get("id") is not None else None,
        exchange_order_id=str(trade.get("order")) if trade.get("order") is not None else None,
        trading_mode=TradingMode.FUTURE.value,
        symbol=trade["symbol"],
        side=trade["side"],
        position_side=position_side.value if position_side is not None else PositionSide.BOTH.value,
        amount=decimal_from_value(trade.get("amount")),
        price=decimal_from_value(trade.get("price")),
        fee=decimal_from_value(fee.get("cost")),
        fee_asset=fee.get("currency"),
        traded_at=datetime_from_milliseconds(trade.get("timestamp")),
        raw=json.dumps(trade, ensure_ascii=False, default=str),
    )


def sync_account_and_positions(strategy: StrategyBase, client: BinanceClient) -> None:
    balance = client.fetch_balance()
    info = balance.get("info") or {}
    cash = first_decimal((balance.get("total") or {}).get(QUOTE_ASSET), info.get("totalWalletBalance"), info.get("totalMarginBalance"))
    equity = first_decimal(info.get("totalMarginBalance"), (balance.get("total") or {}).get(QUOTE_ASSET), cash)
    available = first_decimal((balance.get("free") or {}).get(QUOTE_ASSET), info.get("availableBalance"), cash)
    margin = first_decimal(info.get("totalInitialMargin"), info.get("totalPositionInitialMargin"))
    maintenance_margin = first_decimal(info.get("totalMaintMargin"))
    unrealized_pnl = first_decimal(info.get("totalUnrealizedProfit"))
    strategy.account = Account(
        cash=cash,
        equity=equity,
        available=available,
        margin=margin,
        maintenance_margin=maintenance_margin,
        unrealized_pnl=unrealized_pnl,
    )
    if equity > 0 and maintenance_margin > 0:
        strategy.account.margin_ratio = maintenance_margin / equity

    positions: dict[str, Position] = {}
    for raw_position in client.fetch_positions([SYMBOL]):
        position = position_from_exchange(raw_position)
        if position is None:
            continue
        positions[f"{position.symbol}:{position.side.value}"] = position
    strategy.positions = positions


def position_from_exchange(raw_position: dict) -> Position | None:
    info = raw_position.get("info") or {}
    symbol = raw_position.get("symbol") or info.get("symbol")
    if symbol != SYMBOL:
        return None
    amount = first_decimal(raw_position.get("contracts"), raw_position.get("amount"), info.get("positionAmt"))
    if amount == 0:
        return None
    raw_side = str(raw_position.get("side") or info.get("positionSide") or "").upper()
    side = PositionSide.SHORT if raw_side == "SHORT" or amount < 0 else PositionSide.BOTH
    entry_price = first_decimal(raw_position.get("entryPrice"), info.get("entryPrice"))
    mark_price = first_decimal(raw_position.get("markPrice"), info.get("markPrice"))
    return Position(
        symbol=SYMBOL,
        side=side,
        amount=abs(amount),
        entry_price=entry_price,
        mark_price=mark_price,
        margin=first_decimal(raw_position.get("initialMargin"), info.get("initialMargin"), info.get("positionInitialMargin")),
        liquidation_price=optional_decimal(raw_position.get("liquidationPrice") or info.get("liquidationPrice")),
        unrealized_pnl=first_decimal(raw_position.get("unrealizedPnl"), raw_position.get("unRealizedProfit"), info.get("unRealizedProfit")),
    )


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


def fetch_order_with_retry(client: BinanceClient, order_id: str) -> dict:
    last_error: BinanceClientError | None = None
    for attempt in range(1, ORDER_FETCH_RETRIES + 1):
        try:
            return client.fetch_order(order_id, SYMBOL)
        except BinanceClientError as exc:
            last_error = exc
            if "Order does not exist" not in str(exc) or attempt == ORDER_FETCH_RETRIES:
                raise
            print(f"[{datetime.now():%F %T}] order {order_id} not visible yet, retry {attempt}/{ORDER_FETCH_RETRIES}")
            time.sleep(ORDER_FETCH_RETRY_DELAY_SECONDS)
    raise last_error or BinanceClientError(f"fetch_order failed: order {order_id} not found")


def fetch_order_trades_with_retry(client: BinanceClient, order_id: str) -> list[dict]:
    for attempt in range(1, ORDER_FETCH_RETRIES + 1):
        trades = client.fetch_order_trades(order_id, SYMBOL)
        if trades or attempt == ORDER_FETCH_RETRIES:
            return trades
        print(f"[{datetime.now():%F %T}] order {order_id} trades not visible yet, retry {attempt}/{ORDER_FETCH_RETRIES}")
        time.sleep(ORDER_FETCH_RETRY_DELAY_SECONDS)
    return []


def latest_closed_bars(fetcher: MarketDataFetcher) -> list[BarData]:
    bars = fetcher.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=KLINE_LIMIT)
    if len(bars) < 2:
        return []
    return bars[:-1]


def process_new_closed_bars(strategy: RecursiveCusumReversionFuturesStrategy, bars: list[BarData], last_processed_at: datetime | None) -> datetime | None:
    if not bars:
        return last_processed_at
    data = DataFeed(bars)
    strategy.bind_data(data)
    strategy.on_init()
    if last_processed_at is None:
        last_processed_at = bars[-2].datetime if len(bars) > 1 else None
    for bar in data:
        if last_processed_at is not None and bar.datetime <= last_processed_at:
            continue
        strategy.on_bar(bar)
        last_processed_at = bar.datetime
        print(f"[{datetime.now():%F %T}] processed closed bar {bar.datetime} close={bar.close}")
    return last_processed_at


def configure_futures_account(client: BinanceClient) -> None:
    try:
        client.set_margin_mode(SYMBOL, MARGIN_MODE)
    except BinanceClientError as exc:
        print(f"[{datetime.now():%F %T}] set margin mode skipped: {exc}")
    try:
        client.set_leverage(SYMBOL, int(LEVERAGE))
    except BinanceClientError as exc:
        print(f"[{datetime.now():%F %T}] set leverage skipped: {exc}")


def main() -> None:
    client = BinanceClient(binance_config_from_env())
    client.load_markets()
    configure_futures_account(client)
    fetcher = MarketDataFetcher(client)

    engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(engine)
    Session = create_session_factory(engine)

    strategy = RecursiveCusumReversionFuturesStrategy()
    cycle = 0
    last_processed_at: datetime | None = None

    with Session() as session:
        repository = TradingRepository(session)
        execution_engine = TestnetOrderExecutionEngine(client, repository, RUN_ID)
        strategy.bind_engine(execution_engine)
        sync_account_and_positions(strategy, client)
        run = repository.create_run(
            run_id=RUN_ID,
            name="binance_futures_testnet_recursive_cusum_reversion_strategy",
            run_type="testnet",
            trading_mode=TradingMode.FUTURE.value,
            strategy_name=strategy.name,
            symbols=[SYMBOL],
            timeframe=TIMEFRAME,
            initial_cash=strategy.account.equity,
            config={
                "source": "real/run_testnet_recursive_cusum_reversion_strategy.py",
                "exchange": EXCHANGE,
                "symbol": SYMBOL,
                "timeframe": TIMEFRAME,
                "sandbox": True,
                "threshold": str(THRESHOLD),
                "take_profit_rate": str(TAKE_PROFIT_RATE),
                "stop_loss_rate": str(STOP_LOSS_RATE),
                "position_ratio": str(POSITION_RATIO),
                "leverage": str(LEVERAGE),
                "margin_mode": MARGIN_MODE.value,
                "kline_limit": KLINE_LIMIT,
                "snapshot_interval_seconds": SNAPSHOT_INTERVAL_SECONDS,
                "max_cycles": MAX_CYCLES,
            },
        )
        print(f"started futures testnet CUSUM run: run_id={run.run_id}, symbol={SYMBOL}, timeframe={TIMEFRAME}")

        try:
            while MAX_CYCLES <= 0 or cycle < MAX_CYCLES:
                cycle += 1
                sync_account_and_positions(strategy, client)
                bars = latest_closed_bars(fetcher)
                if not bars:
                    print(f"[{datetime.now():%F %T}] no closed bars fetched")
                else:
                    last_processed_at = process_new_closed_bars(strategy, bars, last_processed_at)
                sync_account_and_positions(strategy, client)
                record_snapshot(repository, strategy, run.run_id)
                print(
                    f"[{datetime.now():%F %T}] snapshot cycle={cycle} "
                    f"equity={strategy.account.equity} available={strategy.account.available} positions={len(strategy.positions)}"
                )
                time.sleep(SNAPSHOT_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="stopped")
            print(f"stopped futures testnet CUSUM run: run_id={run.run_id}")
            return
        except Exception:
            session.rollback()
            repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="failed")
            raise

        strategy.on_stop()
        sync_account_and_positions(strategy, client)
        record_snapshot(repository, strategy, run.run_id)
        repository.finish_run(run.run_id, final_equity=strategy.account.equity, status="finished")
        print(f"finished futures testnet CUSUM run: run_id={run.run_id}")


if __name__ == "__main__":
    main()
