from typing import Any

import ccxt

from crypto_quant.config import BinanceConfig
from crypto_quant.enums import MarginMode, OrderSide, OrderType, PositionSide, TradingMode


class BinanceClient:
    def __init__(self, config: BinanceConfig):
        self.config = config
        self.exchange = ccxt.binance(config.ccxt_options())
        if config.sandbox:
            self.exchange.set_sandbox_mode(True)

    @property  #@property 是 Python 的装饰器，用来把一个类的方法变成可以像属性一样直接访问的 “伪属性”
    def trading_mode(self) -> TradingMode:
        return self.config.trading_mode

    def load_markets(self, reload: bool = False) -> dict[str, Any]:
        return self.exchange.load_markets(reload=reload)

    def fetch_balance(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.exchange.fetch_balance(params or {})

    def fetch_positions(self, symbols: list[str] | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self.trading_mode == TradingMode.SPOT:
            return []
        return self.exchange.fetch_positions(symbols, params or {})

    def set_leverage(self, symbol: str, leverage: int, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.exchange.set_leverage(leverage, symbol, params or {})

    def set_margin_mode(self, symbol: str, margin_mode: MarginMode, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.exchange.set_margin_mode(margin_mode.value, symbol, params or {})

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
        request_params = dict(params or {})
        if self.trading_mode == TradingMode.FUTURE:
            if position_side:
                request_params["positionSide"] = position_side.value
            if reduce_only:
                request_params["reduceOnly"] = True
        if time_in_force:
            request_params["timeInForce"] = time_in_force
        return self.exchange.create_order(symbol, order_type.value, side.value, amount, price, request_params)

    def cancel_order(self, order_id: str, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.exchange.cancel_order(order_id, symbol, params or {})

    def fetch_order(self, order_id: str, symbol: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.exchange.fetch_order(order_id, symbol, params or {})

    def fetch_open_orders(self, symbol: str | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.exchange.fetch_open_orders(symbol, None, None, params or {})

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
