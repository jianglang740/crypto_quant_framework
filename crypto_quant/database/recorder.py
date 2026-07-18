from datetime import datetime
from typing import Any

from crypto_quant.database.models import StrategyRun
from crypto_quant.database.repository import TradingRepository
from crypto_quant.strategy.base import StrategyBase


class LiveDatabaseRecorder:
    def __init__(
        self,
        repository: TradingRepository,
        run_id: str | None = None,
        run_name: str | None = None,
        exchange: str = "okx",
    ):
        self.repository = repository
        self.run_id = run_id
        self.run_name = run_name
        self.exchange = exchange

    def start_run(
        self,
        strategy: StrategyBase,
        symbols: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> StrategyRun:
        run_type = self._run_type(strategy)
        run = self.repository.create_run(
            name=self.run_name or f"{strategy.name}_{run_type}",
            run_type=run_type,
            trading_mode=strategy.trading_mode.value,
            strategy_name=strategy.name,
            symbols=symbols,
            initial_cash=strategy.account.cash,
            config=config,
            run_id=self.run_id,
        )
        self.run_id = run.run_id
        return run

    def record_snapshot(self, strategy: StrategyBase, timestamp: datetime | None = None) -> None:
        self._ensure_run_id()
        self.repository.save_live_snapshot(strategy, self.run_id, timestamp=timestamp)

    def record_orders(self, strategy: StrategyBase) -> None:
        self._ensure_run_id()
        for order in strategy.orders.values():
            self.repository.upsert_local_order(
                order,
                trading_mode=strategy.trading_mode.value,
                run_id=self.run_id,
                strategy_name=strategy.name,
                exchange=self.exchange,
            )

    def finish_run(self, strategy: StrategyBase | None = None, status: str = "finished") -> StrategyRun:
        self._ensure_run_id()
        final_equity = strategy.account.equity if strategy is not None else None
        return self.repository.finish_run(self.run_id, final_equity=final_equity, status=status)

    def _ensure_run_id(self) -> None:
        if self.run_id is None:
            raise RuntimeError("LiveDatabaseRecorder.start_run() must be called first")

    def _run_type(self, strategy: StrategyBase) -> str:
        engine = getattr(strategy, "engine", None)
        config = getattr(engine, "config", None)
        if getattr(config, "dry_run", False):
            return "dry_run"
        return "live"
