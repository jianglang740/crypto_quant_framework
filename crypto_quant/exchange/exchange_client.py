import time
from typing import Any, Callable, TypeVar

import ccxt

from crypto_quant.config import ExchangeConfig
from crypto_quant.enums import MarginMode, OrderSide, OrderType, PositionSide, TradingMode

T = TypeVar("T")


class ExchangeClientError(Exception):
    """Exchange client base exception."""


class ExchangeValidationError(ExchangeClientError):
    """Parameter validation failure (e.g. amount <= 0, spot doesn't support reduce_only)."""


class ExchangeRetryableError(ExchangeClientError):
    """Network, rate-limit, or exchange temporarily unavailable — retryable."""


class ExchangeOrderError(ExchangeClientError):
    """Order placement failure, especially when order status is uncertain."""





class ExchangeClient:
    def __init__(self, config: ExchangeConfig):
        self.config = config
        exchange_class = getattr(ccxt, config.exchange_name)
        self.exchange = exchange_class(config.ccxt_options())
        self.markets: dict[str, Any] = {}
        self.max_read_retries = 3
        self.retry_delay_seconds = 1.0
        if config.sandbox:
            self.exchange.set_sandbox_mode(True)

    # ── exchange-specific info field mappings ──────────────────────

    @property
    def balance_info_fields(self) -> dict[str, list[str]]:
        """Prioritized raw info field names for parsing balance responses."""
        return {
            "equity": ["totalEq"],
            "available": ["adjEq"],
            "margin": ["imr"],
            "maintenance_margin": ["mmr"],
            "unrealized_pnl": ["upl"],
        }

    @property
    def position_info_fields(self) -> dict[str, list[str]]:
        """Prioritized raw info field names for parsing position responses."""
        return {
            "amount": ["pos"],
            "entry_price": ["avgPx"],
            "mark_price": ["markPx"],
            "margin": ["imr"],
            "liquidation_price": ["liqPx"],
            "unrealized_pnl": ["upl"],
        }

    @property
    def exchange_name(self) -> str:
        return self.config.exchange_name

    # ── trading mode ───────────────────────────────────────────────

    @property
    def trading_mode(self) -> TradingMode:
        return self.config.trading_mode

    # ── market info ────────────────────────────────────────────────

    def load_markets(self, reload: bool = False) -> dict[str, Any]:
        self.markets = self._call_read("load_markets", self.exchange.load_markets, reload=reload)
        return self.markets

    def market(self, symbol: str) -> dict[str, Any]:
        if not self.markets:
            self.load_markets()
        market = self.markets.get(symbol)
        if market is None:
            raise ExchangeValidationError(f"unknown symbol on {self.exchange_name}: {symbol}")
        return market

    # ── balance / positions ───────────────────────────────────────

    def fetch_balance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._call_read("fetch_balance", self.exchange.fetch_balance, params or {})

    def fetch_positions(self, symbols: list[str] | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self.trading_mode == TradingMode.SPOT:
            return []
        return self._call_read("fetch_positions", self.exchange.fetch_positions, symbols, params or {})

    def set_leverage(self, symbol: str, leverage: int, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.market(symbol)
        if self.trading_mode != TradingMode.FUTURE:
            raise ExchangeValidationError("set_leverage is only available in futures mode")
        if leverage <= 0:
            raise ExchangeValidationError("leverage must be greater than 0")
        return self._call_write("set_leverage", self.exchange.set_leverage, leverage, symbol, params or {})

    def set_margin_mode(self, symbol: str, margin_mode: MarginMode, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.market(symbol)
        if self.trading_mode != TradingMode.FUTURE:
            raise ExchangeValidationError("set_margin_mode is only available in futures mode")
        return self._call_write("set_margin_mode", self.exchange.set_margin_mode, margin_mode.value, symbol, params or {})

    # ── orders ─────────────────────────────────────────────────────

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
            params=params,
        )

    # ── order validation ───────────────────────────────────────────

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
            raise ExchangeValidationError("order amount must be greater than 0")
        if order_type == OrderType.LIMIT and price is None:
            raise ExchangeValidationError("limit order requires a price")
        if price is not None and price <= 0:
            raise ExchangeValidationError("order price must be greater than 0")
        if self.trading_mode == TradingMode.SPOT and position_side not in (None, PositionSide.BOTH):
            raise ExchangeValidationError("spot orders do not support position_side")
        if self.trading_mode == TradingMode.SPOT and reduce_only:
            raise ExchangeValidationError("spot orders do not support reduce_only")

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
            raise ExchangeValidationError(f"failed to format order amount for {symbol}: {exc}") from exc

    def _format_price(self, symbol: str, price: float | None) -> float | None:
        if price is None:
            return None
        try:
            return float(self.exchange.price_to_precision(symbol, price))
        except Exception as exc:
            raise ExchangeValidationError(f"failed to format order price for {symbol}: {exc}") from exc

    def _validate_amount_limit(self, market: dict[str, Any], amount: float) -> None:
        amount_limits = (market.get("limits") or {}).get("amount") or {}
        minimum = amount_limits.get("min")
        maximum = amount_limits.get("max")
        if minimum is not None and amount < float(minimum):
            raise ExchangeValidationError(f"order amount {amount} is below minimum amount {minimum}")
        if maximum is not None and amount > float(maximum):
            raise ExchangeValidationError(f"order amount {amount} is above maximum amount {maximum}")

    def _validate_price_limit(self, market: dict[str, Any], price: float | None) -> None:
        if price is None:
            return
        price_limits = (market.get("limits") or {}).get("price") or {}
        minimum = price_limits.get("min")
        maximum = price_limits.get("max")
        if minimum is not None and price < float(minimum):
            raise ExchangeValidationError(f"order price {price} is below minimum price {minimum}")
        if maximum is not None and price > float(maximum):
            raise ExchangeValidationError(f"order price {price} is above maximum price {maximum}")

    def _validate_min_notional(self, market: dict[str, Any], amount: float, price: float | None) -> None:
        cost_minimum = ((market.get("limits") or {}).get("cost") or {}).get("min")
        if cost_minimum is None or price is None:
            return
        cost = amount * price
        if cost < float(cost_minimum):
            raise ExchangeValidationError(f"order notional {cost} is below minimum notional {cost_minimum}")

    # ── internal call helpers ──────────────────────────────────────

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
                raise ExchangeClientError(f"{name} failed: {exc}") from exc
        raise ExchangeRetryableError(f"{name} failed after {self.max_read_retries} attempts: {last_error}") from last_error

    def _call_write(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return func(*args, **kwargs)
        except self._retryable_errors() as exc:
            raise ExchangeRetryableError(f"{name} failed with retryable exchange error: {exc}") from exc
        except ccxt.BaseError as exc:
            raise ExchangeClientError(f"{name} failed: {exc}") from exc

    def _call_order(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return func(*args, **kwargs)
        except ExchangeClientError:
            raise
        except self._retryable_errors() as exc:
            raise ExchangeOrderError(f"{name} failed; order status is unknown and was not retried: {exc}") from exc
        except ccxt.BaseError as exc:
            raise ExchangeOrderError(f"{name} failed: {exc}") from exc

    def _retryable_errors(self) -> tuple[type[Exception], ...]:
        return (
            ccxt.NetworkError,
            ccxt.RequestTimeout,
            ccxt.DDoSProtection,
            ccxt.RateLimitExceeded,
            ccxt.ExchangeNotAvailable,
        )


