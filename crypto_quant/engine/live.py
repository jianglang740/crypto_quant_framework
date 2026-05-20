import time
from decimal import Decimal
from typing import Any

from crypto_quant.config import LiveConfig
from crypto_quant.data.feed import DataFeed
from crypto_quant.enums import OrderStatus
from crypto_quant.exchange.binance_client import BinanceClient
from crypto_quant.strategy.base import LocalOrder, OrderRequest, StrategyBase


class LiveEngine:
    def __init__(self, client: BinanceClient, config: LiveConfig | None = None):
        self.client = client
        self.config = config or LiveConfig()
        self.running = False

    def run(self, strategy: StrategyBase, data_provider: Any) -> None:
        strategy.bind_engine(self)
        strategy.on_init()
        strategy.on_start()
        self.running = True
        while self.running:
            bars = data_provider()
            data = bars if isinstance(bars, DataFeed) else DataFeed(bars)
            strategy.bind_data(data)
            for bar in data:
                strategy.on_bar(bar)
            time.sleep(self.config.poll_interval_seconds)
        strategy.on_stop()

    def stop(self) -> None:
        self.running = False

    def submit_order(self, strategy: StrategyBase, request: OrderRequest) -> str:
        if self.config.dry_run:
            order = LocalOrder(id=f"dry-run-{len(strategy.orders) + 1}", request=request, status=OrderStatus.OPEN)
            strategy.orders[order.id] = order
            strategy.on_order(order)
            return order.id
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
        order = LocalOrder(
            id=str(result["id"]),
            request=request,
            status=OrderStatus(result.get("status", OrderStatus.OPEN.value)),
            filled=Decimal(str(result.get("filled") or "0")),
            average=Decimal(str(result["average"])) if result.get("average") is not None else None,
        )
        strategy.orders[order.id] = order
        strategy.on_order(order)
        return order.id

    def cancel_order(self, strategy: StrategyBase, order_id: str) -> None:
        order = strategy.orders[order_id]
        if self.config.dry_run:
            order.status = OrderStatus.CANCELED
            strategy.on_order(order)
            return
        self.client.cancel_order(order_id, order.request.symbol)
        order.status = OrderStatus.CANCELED
        strategy.on_order(order)
