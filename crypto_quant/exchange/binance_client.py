import time
from typing import Any, Callable, TypeVar

import ccxt

from crypto_quant.config import BinanceConfig
from crypto_quant.enums import MarginMode, OrderSide, OrderType, PositionSide, TradingMode

T = TypeVar("T")


class BinanceClientError(Exception): #BinanceClient 总异常基类
    pass


class BinanceValidationError(BinanceClientError): #参数验证失败，比如数量小于 0、spot 不支持 reduce_only
    pass


class BinanceRetryableError(BinanceClientError): #	网络、限频、交易所暂不可用这类可重试错误
    pass


class BinanceOrderError(BinanceClientError): #	下单失败，尤其是订单状态不确定
    pass


class BinanceClient:
    def __init__(self, config: BinanceConfig):
        self.config = config
        self.exchange = ccxt.binance(config.ccxt_options()) #创建交易所实例
        self.markets: dict[str, Any] = {} #交易所的交易对信息
        self.max_read_retries = 3
        self.retry_delay_seconds = 1.0
        if config.sandbox:
            self.exchange.set_sandbox_mode(True)

    @property
    def trading_mode(self) -> TradingMode:
        return self.config.trading_mode

    def load_markets(self, reload: bool = False) -> dict[str, Any]:
        self.markets = self._call_read("load_markets", self.exchange.load_markets, reload=reload)
        return self.markets

    def market(self, symbol: str) -> dict[str, Any]:
        if not self.markets:
            self.load_markets()
        market = self.markets.get(symbol)
        if market is None:
            raise BinanceValidationError(f"unknown Binance symbol: {symbol}")
        return market

    def fetch_balance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._call_read("fetch_balance", self.exchange.fetch_balance, params or {})

    def fetch_positions(self, symbols: list[str] | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self.trading_mode == TradingMode.SPOT:
            return []
        return self._call_read("fetch_positions", self.exchange.fetch_positions, symbols, params or {})

    def set_leverage(self, symbol: str, leverage: int, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.market(symbol)
        if self.trading_mode != TradingMode.FUTURE:
            raise BinanceValidationError("set_leverage is only available in futures mode")
        if leverage <= 0:
            raise BinanceValidationError("leverage must be greater than 0")
        return self._call_write("set_leverage", self.exchange.set_leverage, leverage, symbol, params or {})

    def set_margin_mode(self, symbol: str, margin_mode: MarginMode, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.market(symbol)
        if self.trading_mode != TradingMode.FUTURE:
            raise BinanceValidationError("set_margin_mode is only available in futures mode")
        return self._call_write("set_margin_mode", self.exchange.set_margin_mode, margin_mode.value, symbol, params or {})

    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: float | None = None,
        position_side: PositionSide | None = None,
        reduce_only: bool = False,
        time_in_force: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        market = self.market(symbol)
        formatted_amount, formatted_price = self.validate_order(
            market=market,
            symbol=symbol,
            order_type=order_type,
            amount=amount,
            price=price,
            position_side=position_side,
            reduce_only=reduce_only,
        )
        request_params = dict(params or {})
        if self.trading_mode == TradingMode.FUTURE:
            if position_side:
                request_params["positionSide"] = position_side.value
            if reduce_only:
                request_params["reduceOnly"] = True
        if time_in_force:
            request_params["timeInForce"] = time_in_force
        return self._call_order(
            "create_order",
            self.exchange.create_order,
            symbol,
            order_type.value,
            side.value,
            formatted_amount,
            formatted_price,
            request_params,
        )

    def cancel_order(self, order_id: str, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.market(symbol)
        return self._call_read("cancel_order", self.exchange.cancel_order, order_id, symbol, params or {})

    def fetch_order(self, order_id: str, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.market(symbol)
        return self._call_read("fetch_order", self.exchange.fetch_order, order_id, symbol, params or {})

    def fetch_open_orders(self, symbol: str | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if symbol is not None:
            self.market(symbol)
        return self._call_read("fetch_open_orders", self.exchange.fetch_open_orders, symbol, None, None, params or {})

    def fetch_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if symbol is not None:
            self.market(symbol)
        return self._call_read("fetch_orders", self.exchange.fetch_orders, symbol, since, limit, params or {})

    def fetch_closed_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if symbol is not None:
            self.market(symbol)
        return self._call_read("fetch_closed_orders", self.exchange.fetch_closed_orders, symbol, since, limit, params or {})

    def fetch_canceled_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if symbol is not None:
            self.market(symbol)
        return self._call_read("fetch_canceled_orders", self.exchange.fetch_canceled_orders, symbol, since, limit, params or {})

    def fetch_my_trades(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if symbol is not None:
            self.market(symbol)
        return self._call_read("fetch_my_trades", self.exchange.fetch_my_trades, symbol, since, limit, params or {})

    def fetch_order_trades(self, order_id: str, symbol: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        request_params = dict(params or {})
        request_params["orderId"] = order_id
        return self.fetch_my_trades(symbol=symbol, params=request_params)

    def close_position(
        self,
        symbol: str,
        amount: float,
        position_side: PositionSide = PositionSide.BOTH,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        side = OrderSide.SELL if position_side != PositionSide.SHORT else OrderSide.BUY
        return self.create_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            amount=amount,
            position_side=position_side if self.trading_mode == TradingMode.FUTURE else None,
            reduce_only=self.trading_mode == TradingMode.FUTURE,
            params=params,
        )

    def validate_order(
        self,
        market: dict[str, Any],
        symbol: str,
        order_type: OrderType,
        amount: float,
        price: float | None = None,
        position_side: PositionSide | None = None,
        reduce_only: bool = False,
    ) -> tuple[float, float | None]:
        if amount <= 0:
            raise BinanceValidationError("order amount must be greater than 0")
        if order_type == OrderType.LIMIT and price is None:
            raise BinanceValidationError("limit order requires a price")
        if price is not None and price <= 0:
            raise BinanceValidationError("order price must be greater than 0")
        if self.trading_mode == TradingMode.SPOT and position_side not in (None, PositionSide.BOTH):
            raise BinanceValidationError("spot orders do not support position_side")
        if self.trading_mode == TradingMode.SPOT and reduce_only:
            raise BinanceValidationError("spot orders do not support reduce_only")

        formatted_amount = self._format_amount(symbol, amount)
        formatted_price = self._format_price(symbol, price) if price is not None else None
        self._validate_amount_limit(market, formatted_amount)
        self._validate_price_limit(market, formatted_price)
        self._validate_min_notional(market, formatted_amount, formatted_price)
        return formatted_amount, formatted_price

    def _format_amount(self, symbol: str, amount: float) -> float:
        try:
            return float(self.exchange.amount_to_precision(symbol, amount))
        except Exception as exc:
            raise BinanceValidationError(f"failed to format order amount for {symbol}: {exc}") from exc

    def _format_price(self, symbol: str, price: float | None) -> float | None:
        if price is None:
            return None
        try:
            return float(self.exchange.price_to_precision(symbol, price))
        except Exception as exc:
            raise BinanceValidationError(f"failed to format order price for {symbol}: {exc}") from exc

    def _validate_amount_limit(self, market: dict[str, Any], amount: float) -> None:
        amount_limits = (market.get("limits") or {}).get("amount") or {}
        minimum = amount_limits.get("min")
        maximum = amount_limits.get("max")
        if minimum is not None and amount < float(minimum):
            raise BinanceValidationError(f"order amount {amount} is below minimum amount {minimum}")
        if maximum is not None and amount > float(maximum):
            raise BinanceValidationError(f"order amount {amount} is above maximum amount {maximum}")

    def _validate_price_limit(self, market: dict[str, Any], price: float | None) -> None:
        if price is None:
            return
        price_limits = (market.get("limits") or {}).get("price") or {}
        minimum = price_limits.get("min")
        maximum = price_limits.get("max")
        if minimum is not None and price < float(minimum):
            raise BinanceValidationError(f"order price {price} is below minimum price {minimum}")
        if maximum is not None and price > float(maximum):
            raise BinanceValidationError(f"order price {price} is above maximum price {maximum}")

    def _validate_min_notional(self, market: dict[str, Any], amount: float, price: float | None) -> None:
        cost_minimum = ((market.get("limits") or {}).get("cost") or {}).get("min")
        if cost_minimum is None or price is None:
            return
        cost = amount * price
        if cost < float(cost_minimum):
            raise BinanceValidationError(f"order notional {cost} is below minimum notional {cost_minimum}")

    def _call_read(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        last_error: Exception | None = None
        for attempt in range(self.max_read_retries):
            try:
                return func(*args, **kwargs)
            except self._retryable_errors() as exc:
                last_error = exc
                if attempt == self.max_read_retries - 1:
                    break
                time.sleep(self.retry_delay_seconds)
            except ccxt.BaseError as exc:
                raise BinanceClientError(f"{name} failed: {exc}") from exc
        raise BinanceRetryableError(f"{name} failed after {self.max_read_retries} attempts: {last_error}") from last_error

    def _call_write(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return func(*args, **kwargs)
        except self._retryable_errors() as exc:
            raise BinanceRetryableError(f"{name} failed with retryable exchange error: {exc}") from exc
        except ccxt.BaseError as exc:
            raise BinanceClientError(f"{name} failed: {exc}") from exc

    def _call_order(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return func(*args, **kwargs)
        except BinanceClientError:
            raise
        except self._retryable_errors() as exc:
            raise BinanceOrderError(f"{name} failed; order status is unknown and was not retried: {exc}") from exc
        except ccxt.BaseError as exc:
            raise BinanceOrderError(f"{name} failed: {exc}") from exc

    def _retryable_errors(self) -> tuple[type[Exception], ...]:
        return (
            ccxt.NetworkError,
            ccxt.RequestTimeout,
            ccxt.DDoSProtection,
            ccxt.RateLimitExceeded,
            ccxt.ExchangeNotAvailable,
        )
