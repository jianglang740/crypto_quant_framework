import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from crypto_quant.config import LiveConfig
from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.enums import OrderSide, OrderStatus, OrderType, PositionSide, TimeInForce, TradingMode
from crypto_quant.strategy.base import Account, LocalOrder, OrderRequest, Position, StrategyBase, Trade

if TYPE_CHECKING:
    from crypto_quant.exchange.binance_client import BinanceClient


class LiveEngine:
    def __init__(self, client: "BinanceClient", config: LiveConfig | None = None):
        self.client = client
        self.config = config or LiveConfig()
        self.running = False
        self.current_bar: BarData | None = None
        self.orders: dict[str, LocalOrder] = {}
        self.trades: list[Trade] = []
        self._last_bar_datetime: dict[tuple[str, str], object] = {}
        self._last_sync_at = 0.0

    def run(self, strategy: StrategyBase, data_provider: Any) -> None:
        strategy.bind_engine(self)
        self._initialize_strategy_state(strategy)
        strategy.on_init()
        if not self.config.dry_run and self.config.sync_on_start:
            self.sync_state(strategy)
        strategy.on_start()
        self.running = True
        while self.running:
            bars = data_provider()
            data = bars if isinstance(bars, DataFeed) else DataFeed(bars)
            new_bars = self._new_bars(data)
            if new_bars:
                data = DataFeed(new_bars)
                strategy.bind_data(data)
                for bar in data:
                    self.current_bar = bar
                    if self.config.dry_run:
                        self._mark_to_market(strategy, bar)
                        self._fill_open_orders(strategy)
                    strategy.on_bar(bar)
                    if self.config.dry_run:
                        self._mark_to_market(strategy, bar)
            if not self.config.dry_run and self._should_sync():
                self.sync_state(strategy)
            time.sleep(self.config.poll_interval_seconds)
        strategy.on_stop()

    def stop(self) -> None:
        self.running = False

    def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        if self.config.dry_run:
            return self._submit_dry_run_order(strategy, request)
        try:
            result = self.client.create_order(
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                amount=float(request.amount),
                price=float(request.price) if request.price is not None else None,
                position_side=request.position_side,
                reduce_only=request.reduce_only,
                time_in_force=request.time_in_force.value if request.time_in_force else None,
                params=request.params,
            )
        except self._binance_client_errors():
            order = LocalOrder(id=f"rejected-{uuid4()}", request=request, status=OrderStatus.REJECTED)
            self.orders[order.id] = order
            strategy.orders[order.id] = order
            strategy.on_order(order)
            return order.id
        order = LocalOrder(
            id=str(result.get("id") or result.get("clientOrderId") or uuid4()),
            request=request,
            status=self._parse_order_status(result.get("status")),
            filled=self._parse_decimal(result.get("filled")),
            average=self._parse_optional_decimal(result.get("average")),
        )
        self.orders[order.id] = order
        strategy.orders[order.id] = order
        strategy.on_order(order)
        return order.id

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None:
        order = strategy.orders[order_id]
        if self.config.dry_run:
            order.status = OrderStatus.CANCELED
            strategy.on_order(order)
            return
        result = self.client.cancel_order(order_id, order.request.symbol)
        order.status = self._parse_order_status(result.get("status")) if isinstance(result, dict) else OrderStatus.CANCELED
        strategy.on_order(order)

    def sync_state(self, strategy: StrategyBase) -> None:
        if self.config.dry_run:
            return
        self._sync_account(strategy)
        self._sync_positions(strategy)
        self._sync_open_orders(strategy)
        self._last_sync_at = time.monotonic()

    def _initialize_strategy_state(self, strategy: StrategyBase) -> None:
        self.orders = {}
        self.trades = []
        self.current_bar = None
        strategy.orders = {}
        strategy.trades = []
        strategy.positions = {}
        if self.config.dry_run:
            strategy.account = Account(
                cash=self.config.initial_cash,
                equity=self.config.initial_cash,
                available=self.config.initial_cash,
            )

    def _new_bars(self, data: DataFeed) -> list[BarData]:
        bars = []
        for bar in data.bars:
            key = (bar.symbol, bar.timeframe)
            last_datetime = self._last_bar_datetime.get(key)
            if last_datetime is None or bar.datetime > last_datetime:
                bars.append(bar)
                self._last_bar_datetime[key] = bar.datetime
        return bars

    def _should_sync(self) -> bool:
        if self.config.sync_interval_seconds <= 0:
            return False
        return time.monotonic() - self._last_sync_at >= self.config.sync_interval_seconds

    def _sync_account(self, strategy: StrategyBase) -> None:
        balance = self.client.fetch_balance()
        info = balance.get("info") or {}
        quote = self.config.account_quote_asset
        free = balance.get("free") or {}
        total = balance.get("total") or {}
        cash = self._first_decimal(total.get(quote), info.get("totalWalletBalance"), info.get("totalMarginBalance"))
        equity = self._first_decimal(info.get("totalMarginBalance"), total.get(quote), cash)
        available = self._first_decimal(free.get(quote), info.get("availableBalance"), cash)
        margin = self._first_decimal(info.get("totalInitialMargin"), info.get("totalPositionInitialMargin"))
        maintenance_margin = self._first_decimal(info.get("totalMaintMargin"))
        unrealized_pnl = self._first_decimal(info.get("totalUnrealizedProfit"))
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

    def _sync_positions(self, strategy: StrategyBase) -> None:
        raw_positions = self.client.fetch_positions(self.config.sync_symbols or None)
        positions: dict[str, Position] = {}
        for raw_position in raw_positions:
            info = raw_position.get("info") or {}
            symbol = raw_position.get("symbol") or info.get("symbol")
            if not symbol:
                continue
            amount = self._first_decimal(raw_position.get("contracts"), raw_position.get("amount"), info.get("positionAmt"))
            if amount == 0:
                continue
            side = self._parse_position_side(raw_position.get("side") or info.get("positionSide"), amount)
            position_amount = abs(amount) if side == PositionSide.SHORT else amount
            position = Position(
                symbol=str(symbol),
                side=side,
                amount=position_amount,
                entry_price=self._first_decimal(raw_position.get("entryPrice"), info.get("entryPrice")),
                mark_price=self._first_decimal(raw_position.get("markPrice"), info.get("markPrice")),
                margin=self._first_decimal(raw_position.get("initialMargin"), info.get("initialMargin"), info.get("positionInitialMargin")),
                liquidation_price=self._parse_optional_decimal(raw_position.get("liquidationPrice") or info.get("liquidationPrice")),
                unrealized_pnl=self._first_decimal(raw_position.get("unrealizedPnl"), raw_position.get("unRealizedProfit"), raw_position.get("unrealizedProfit"), info.get("unRealizedProfit"), info.get("unrealizedProfit")),
            )
            positions[f"{position.symbol}:{position.side.value}"] = position
        strategy.positions = positions

    def _sync_open_orders(self, strategy: StrategyBase) -> None:
        raw_orders = []
        if self.config.sync_symbols:
            for symbol in self.config.sync_symbols:
                raw_orders.extend(self.client.fetch_open_orders(symbol))
        else:
            raw_orders = self.client.fetch_open_orders()
        orders: dict[str, LocalOrder] = {}
        for raw_order in raw_orders:
            order = self._local_order_from_exchange(raw_order)
            orders[order.id] = order
        self.orders = orders
        strategy.orders = orders

    def _local_order_from_exchange(self, raw_order: dict[str, Any]) -> LocalOrder:
        info = raw_order.get("info") or {}
        price = self._parse_optional_decimal(raw_order.get("price") or info.get("price"))
        request = OrderRequest(
            symbol=str(raw_order.get("symbol") or info.get("symbol")),
            side=self._parse_order_side(raw_order.get("side") or info.get("side")),
            order_type=self._parse_order_type(raw_order.get("type") or info.get("type"), price),
            amount=self._first_decimal(raw_order.get("amount"), info.get("origQty"), info.get("quantity")),
            price=price,
            position_side=self._parse_position_side(info.get("positionSide"), None),
            reduce_only=self._parse_bool(raw_order.get("reduceOnly") or info.get("reduceOnly")),
            time_in_force=self._parse_time_in_force(raw_order.get("timeInForce") or info.get("timeInForce")),
            params=info,
        )
        return LocalOrder(
            id=str(raw_order.get("id") or raw_order.get("clientOrderId") or info.get("orderId") or uuid4()),
            request=request,
            status=self._parse_order_status(raw_order.get("status") or info.get("status")),
            filled=self._first_decimal(raw_order.get("filled"), info.get("executedQty")),
            average=self._parse_optional_decimal(raw_order.get("average") or info.get("avgPrice")),
        )

    def _first_decimal(self, *values: Any) -> Decimal:
        for value in values:
            if value not in (None, ""):
                return self._parse_decimal(value)
        return Decimal("0")

    def _parse_decimal(self, value: Any, default: str = "0") -> Decimal:
        if value in (None, ""):
            return Decimal(default)
        return Decimal(str(value))

    def _parse_optional_decimal(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    def _parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return False
        return str(value).lower() in {"1", "true", "yes"}

    def _parse_order_status(self, value: Any) -> OrderStatus:
        if value in (None, ""):
            return OrderStatus.OPEN
        normalized = str(value).lower()
        for status in OrderStatus:
            if normalized in {status.value.lower(), status.name.lower()}:
                return status
        return OrderStatus.OPEN

    def _parse_order_side(self, value: Any) -> OrderSide:
        normalized = str(value or OrderSide.BUY.value).lower()
        return OrderSide.SELL if normalized == OrderSide.SELL.value else OrderSide.BUY

    def _parse_order_type(self, value: Any, price: Decimal | None = None) -> OrderType:
        if value in (None, ""):
            return OrderType.LIMIT if price is not None else OrderType.MARKET
        normalized = str(value)
        for order_type in OrderType:
            if normalized.lower() in {order_type.value.lower(), order_type.name.lower()}:
                return order_type
        return OrderType.LIMIT if price is not None else OrderType.MARKET

    def _parse_position_side(self, value: Any, amount: Decimal | None = None) -> PositionSide:
        if value not in (None, ""):
            normalized = str(value).upper()
            for side in PositionSide:
                if normalized in {side.value.upper(), side.name.upper()}:
                    return side
            if normalized == "LONG":
                return PositionSide.LONG
            if normalized == "SHORT":
                return PositionSide.SHORT
        if amount is not None:
            return PositionSide.SHORT if amount < 0 else PositionSide.LONG
        return PositionSide.BOTH

    def _parse_time_in_force(self, value: Any) -> TimeInForce | None:
        if value in (None, ""):
            return None
        normalized = str(value).upper()
        for time_in_force in TimeInForce:
            if normalized in {time_in_force.value.upper(), time_in_force.name.upper()}:
                return time_in_force
        return None

    def _binance_client_errors(self) -> tuple[type[Exception], ...]:
        try:
            from crypto_quant.exchange.binance_client import BinanceClientError
        except ImportError:
            return (Exception,)
        return (BinanceClientError,)

    def _submit_dry_run_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        order = LocalOrder(id=f"dry-run-{len(self.orders) + 1}", request=request, status=OrderStatus.OPEN)
        self.orders[order.id] = order
        strategy.orders[order.id] = order
        strategy.on_order(order)
        self._fill_order(strategy, order)
        return order.id

    def _fill_open_orders(self, strategy: StrategyBase) -> None:
        for order in list(self.orders.values()):
            if order.status == OrderStatus.OPEN:
                self._fill_order(strategy, order)

    def _fill_order(self, strategy: StrategyBase, order: LocalOrder) -> None:
        if self.current_bar is None:
            return
        request = order.request
        fill_price = request.price or self.current_bar.close
        if request.price is not None:
            if request.side == OrderSide.BUY and request.price < self.current_bar.low:
                return
            if request.side == OrderSide.SELL and request.price > self.current_bar.high:
                return
        slippage = fill_price * self.config.slippage_rate
        fill_price = fill_price + slippage if request.side == OrderSide.BUY else fill_price - slippage
        notional = fill_price * request.amount
        fee = notional * self.config.commission_rate
        trade = Trade(
            id=str(uuid4()),
            symbol=request.symbol,
            side=request.side,
            amount=request.amount,
            price=fill_price,
            fee=fee,
            traded_at=self.current_bar.datetime,
        )
        filled = self._apply_trade(strategy, trade, request.position_side, request.reduce_only)
        if not filled:
            order.status = OrderStatus.REJECTED
            strategy.on_order(order)
            return
        order.filled = request.amount
        order.average = fill_price
        order.status = OrderStatus.CLOSED
        self.trades.append(trade)
        strategy.trades.append(trade)
        strategy.on_trade(trade)
        strategy.on_order(order)

    def _apply_trade(
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        if strategy.trading_mode == TradingMode.FUTURE:
            return self._apply_futures_trade(strategy, trade, position_side, reduce_only)
        return self._apply_spot_trade(strategy, trade, position_side, reduce_only)

    def _apply_spot_trade(
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        side = position_side or PositionSide.BOTH
        position = strategy.get_position(trade.symbol, side)
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
        previous_amount = position.amount
        new_amount = previous_amount + signed_amount
        if reduce_only and abs(signed_amount) > abs(previous_amount):
            return False
        notional = trade.price * trade.amount
        cash_change = -(notional + trade.fee) if trade.side == OrderSide.BUY else notional - trade.fee
        if strategy.account.cash + cash_change < 0:
            return False
        if reduce_only:
            strategy.account.realized_pnl += self._realized_pnl(position, trade)
        elif previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0):
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
        else:
            strategy.account.realized_pnl += self._realized_pnl(position, trade)
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                position.entry_price = trade.price
        position.amount = new_amount
        position.mark_price = trade.price
        strategy.account.cash += cash_change
        strategy.account.available = strategy.account.cash
        return True

    def _apply_futures_trade(
        self,
        strategy: StrategyBase,
        trade: Trade,
        position_side: PositionSide | None,
        reduce_only: bool,
    ) -> bool:
        side = position_side or PositionSide.BOTH
        position = strategy.get_position(trade.symbol, side)
        signed_amount = trade.amount if trade.side == OrderSide.BUY else -trade.amount
        if side == PositionSide.SHORT:
            signed_amount = -signed_amount
        previous_amount = position.amount
        new_amount = previous_amount + signed_amount
        if reduce_only and (previous_amount == 0 or abs(signed_amount) > abs(previous_amount)):
            return False
        if previous_amount != 0 and (previous_amount > 0) != (signed_amount > 0) and abs(signed_amount) > abs(previous_amount):
            return False

        notional = trade.price * trade.amount
        leverage = self.config.leverage if self.config.leverage > 0 else Decimal("1")
        is_opening = previous_amount == 0 or (previous_amount > 0) == (signed_amount > 0)
        if is_opening and not reduce_only:
            required_margin = notional / leverage
            if strategy.account.available < required_margin + trade.fee:
                return False
            total_cost = position.entry_price * abs(previous_amount) + notional
            position.entry_price = total_cost / abs(new_amount)
            position.margin += required_margin
            strategy.account.margin += required_margin
            strategy.account.cash -= trade.fee
        else:
            close_amount = min(abs(trade.amount), abs(previous_amount))
            close_ratio = close_amount / abs(previous_amount)
            released_margin = position.margin * close_ratio
            realized_pnl = self._realized_pnl(position, trade)
            strategy.account.realized_pnl += realized_pnl
            strategy.account.cash += realized_pnl
            position.margin -= released_margin
            strategy.account.margin -= released_margin
            if new_amount != 0 and abs(signed_amount) > abs(previous_amount):
                opened_amount = abs(signed_amount) - abs(previous_amount)
                opened_notional = trade.price * opened_amount
                required_margin = opened_notional / leverage
                if strategy.account.available < required_margin:
                    return False
                position.entry_price = trade.price
                position.margin += required_margin
                strategy.account.margin += required_margin
            elif new_amount == 0:
                position.entry_price = Decimal("0")
                position.margin = Decimal("0")
        position.amount = new_amount
        position.mark_price = trade.price
        if self.current_bar is not None:
            self._mark_to_market(strategy, self.current_bar)
        return True

    def _realized_pnl(self, position: Position, trade: Trade) -> Decimal:
        if position.side == PositionSide.SHORT:
            return (position.entry_price - trade.price) * trade.amount - trade.fee
        return (trade.price - position.entry_price) * trade.amount - trade.fee

    def _liquidation_price(self, position: Position) -> Decimal | None:
        if position.amount == 0 or position.entry_price == 0:
            return None
        leverage = self.config.leverage if self.config.leverage > 0 else Decimal("1")
        if position.side == PositionSide.SHORT:
            return position.entry_price * (Decimal("1") + Decimal("1") / leverage - self.config.maintenance_margin_rate)
        return position.entry_price * (Decimal("1") - Decimal("1") / leverage + self.config.maintenance_margin_rate)

    def _mark_to_market(self, strategy: StrategyBase, bar: BarData) -> None:
        unrealized = Decimal("0")
        position_value = Decimal("0")
        maintenance_margin = Decimal("0")
        for position in strategy.positions.values():
            position.mark_price = bar.close
            if position.amount == 0:
                position.unrealized_pnl = Decimal("0")
                continue
            if position.side == PositionSide.SHORT:
                position.unrealized_pnl = (position.entry_price - bar.close) * abs(position.amount)
            else:
                position.unrealized_pnl = (bar.close - position.entry_price) * position.amount
                position_value += bar.close * position.amount
            if strategy.trading_mode == TradingMode.FUTURE:
                maintenance_margin += bar.close * abs(position.amount) * self.config.maintenance_margin_rate
                position.liquidation_price = self._liquidation_price(position)
            unrealized += position.unrealized_pnl
        strategy.account.unrealized_pnl = unrealized
        if strategy.trading_mode == TradingMode.FUTURE:
            strategy.account.maintenance_margin = maintenance_margin
            strategy.account.equity = strategy.account.cash + unrealized
            strategy.account.available = strategy.account.equity - strategy.account.margin
            if maintenance_margin == 0:
                strategy.account.margin_ratio = Decimal("0")
            else:
                strategy.account.margin_ratio = maintenance_margin / strategy.account.equity if strategy.account.equity > 0 else Decimal("Infinity")
        else:
            strategy.account.maintenance_margin = Decimal("0")
            strategy.account.margin_ratio = Decimal("0")
            strategy.account.equity = strategy.account.cash + position_value
            strategy.account.available = strategy.account.cash
