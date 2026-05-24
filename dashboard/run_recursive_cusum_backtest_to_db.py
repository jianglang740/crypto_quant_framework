from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.analysis import PerformanceAnalyzer
from crypto_quant.config import BacktestConfig, MySQLConfig
from crypto_quant.data import load_bars_from_csv
from crypto_quant.database import TradingRepository, create_all_tables, create_mysql_engine, create_session_factory
from crypto_quant.engine import BacktestEngine
from crypto_quant.enums import TradingMode
from my_strategys.run_recursive_cusum_reversion_strategy import RecursiveCusumReversionFuturesStrategy


DEFAULT_CSV = "/Users/clinking/开发/quant/data/ETH_USDT_5m_1year.csv"


def main() -> None:
    args = parse_args()
    data = load_bars_from_csv(
        path=args.csv,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    strategy = RecursiveCusumReversionFuturesStrategy(
        threshold=Decimal(args.threshold),
        take_profit_rate=Decimal(args.take_profit_rate),
        stop_loss_rate=Decimal(args.stop_loss_rate),
        position_ratio=Decimal(args.position_ratio),
    )
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=Decimal(args.initial_cash),
            commission_rate=Decimal(args.commission_rate),
            slippage_rate=Decimal(args.slippage_rate),
            leverage=Decimal(args.leverage),
        )
    )
    result = engine.run(strategy, data)
    report = PerformanceAnalyzer().analyze(result.equity_curve, result.trades)

    mysql_engine = create_mysql_engine(mysql_config_from_env())
    create_all_tables(mysql_engine)
    Session = create_session_factory(mysql_engine)
    with Session() as session:
        repository = TradingRepository(session)
        run = repository.save_backtest_result(
            result,
            strategy_name=strategy.name,
            trading_mode=TradingMode.FUTURE.value,
            run_id=args.run_id,
            run_name=args.run_name,
            symbols=[args.symbol],
            timeframe=args.timeframe,
            config={
                "source": "dashboard/run_recursive_cusum_backtest_to_db.py",
                "purpose": "dashboard_test_backtest_display",
                "csv": str(args.csv),
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "threshold": args.threshold,
                "take_profit_rate": args.take_profit_rate,
                "stop_loss_rate": args.stop_loss_rate,
                "position_ratio": args.position_ratio,
                "initial_cash": args.initial_cash,
                "commission_rate": args.commission_rate,
                "slippage_rate": args.slippage_rate,
                "leverage": args.leverage,
            },
        )

    print("recursive CUSUM backtest saved for dashboard")
    print(f"run_id={run.run_id}")
    print(f"run_name={run.name}")
    print(f"strategy={strategy.name}")
    print(f"symbol={args.symbol}")
    print(f"timeframe={args.timeframe}")
    print(f"bars={len(data.bars)}")
    print(f"orders={len(result.orders)}")
    print(f"trades={len(result.trades)}")
    print(f"initial_equity={report.initial_equity}")
    print(f"final_equity={report.final_equity}")
    print(f"total_return={report.total_return}")
    print(f"max_drawdown={report.max_drawdown}")
    print(f"sharpe_ratio={report.sharpe_ratio}")
    print(f"win_rate={report.win_rate}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run recursive CUSUM futures backtest and save result into MySQL for dashboard testing.")
    parser.add_argument("--csv", type=Path, default=Path(DEFAULT_CSV))
    parser.add_argument("--symbol", default="ETH/USDT")
    parser.add_argument("--timeframe", default="5m")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser.add_argument("--run-id", default=f"dash_cusum_bt_{timestamp}")
    parser.add_argument("--run-name", default=f"Dashboard Test - Recursive CUSUM Reversion Backtest {timestamp}")
    parser.add_argument("--threshold", default="0.07")
    parser.add_argument("--take-profit-rate", default="0.018")
    parser.add_argument("--stop-loss-rate", default="0.033")
    parser.add_argument("--position-ratio", default="0.30")
    parser.add_argument("--initial-cash", default="10000")
    parser.add_argument("--commission-rate", default="0.001")
    parser.add_argument("--slippage-rate", default="0")
    parser.add_argument("--leverage", default="10")
    return parser.parse_args()


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE", "crypto_quant"),
    )


if __name__ == "__main__":
    main()