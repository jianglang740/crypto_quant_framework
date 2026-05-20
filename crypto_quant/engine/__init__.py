from crypto_quant.engine.backtest import BacktestEngine, BacktestResult

__all__ = ["BacktestEngine", "BacktestResult", "LiveEngine"]


def __getattr__(name: str):
    if name == "LiveEngine":
        from crypto_quant.engine.live import LiveEngine

        return LiveEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
