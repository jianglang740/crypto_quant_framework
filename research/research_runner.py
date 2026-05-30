from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from crypto_quant.analysis.performance import PerformanceAnalyzer, PerformanceReport
from crypto_quant.config import BacktestConfig, MySQLConfig
from crypto_quant.data.feed import DataFeed
from crypto_quant.database import MarketDataRepository, TradingRepository, create_mysql_engine, create_session_factory
from crypto_quant.engine.backtest import BacktestEngine, BacktestResult

from research.search_space import CandidateSpec, build_search_space

PERIODS_PER_YEAR_5M = 365 * 24 * 12


@dataclass(frozen=True, slots=True)
class CandidateResult:
    spec: CandidateSpec
    train_result: BacktestResult
    validation_result: BacktestResult
    train_metrics: dict[str, Any]
    validation_metrics: dict[str, Any]
    score: float


def mysql_config_from_env() -> MySQLConfig:
    return MySQLConfig(
        host=os.getenv("CRYPTO_QUANT_MYSQL_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("CRYPTO_QUANT_MYSQL_PORT") or os.getenv("MYSQL_PORT", "3306")),
        username=os.getenv("CRYPTO_QUANT_MYSQL_USERNAME") or os.getenv("MYSQL_USER", "root"),
        password=os.getenv("CRYPTO_QUANT_MYSQL_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("CRYPTO_QUANT_MYSQL_DATABASE") or os.getenv("MYSQL_DATABASE", "crypto_quant"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded strategy research with existing framework components.")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--strategy")
    parser.add_argument("--max-runs", type=int, default=50)
    parser.add_argument("--min-bars", type=int, default=1000)
    parser.add_argument("--train-ratio", type=Decimal, default=Decimal("0.7"))
    parser.add_argument("--initial-cash", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--commission-rate", type=Decimal, default=Decimal("0.0004"))
    parser.add_argument("--slippage-rate", type=Decimal, default=Decimal("0"))
    parser.add_argument("--leverage", type=Decimal, default=Decimal("3"))
    parser.add_argument("--save-best", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = create_mysql_engine(mysql_config_from_env())
    Session = create_session_factory(engine)

    with Session() as session:
        market_repository = MarketDataRepository(session)
        data = market_repository.get_data_feed(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start=parse_datetime(args.start),
            end=parse_datetime(args.end),
            exchange=args.exchange,
            limit=args.limit,
        )
        validate_data(data, args.min_bars)
        train_data, validation_data = split_data(data, args.train_ratio)
        print_data_summary(args, data, train_data, validation_data)

        specs = build_search_space(args.strategy, args.max_runs)
        results = run_candidates(args, specs, train_data, validation_data)
        ranked = sorted(results, key=lambda item: item.score, reverse=True)
        print_ranked_candidates(ranked[:10])

        qualified = [item for item in ranked if passes_basic_filters(item.validation_metrics)]
        if not qualified:
            print("no qualified candidate found")
            return

        best = qualified[0]
        print_best_candidate(best)
        if args.save_best:
            trading_repository = TradingRepository(session)
            saved_run = save_best_result(args, trading_repository, data, best)
            print(f"saved_run_id={saved_run.run_id}")
            print(f"saved_run_name={saved_run.name}")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def validate_data(data: DataFeed, min_bars: int) -> None:
    if len(data) < min_bars:
        raise ValueError(f"not enough bars: bars={len(data)}, min_bars={min_bars}")


def split_data(data: DataFeed, train_ratio: Decimal) -> tuple[DataFeed, DataFeed]:
    if train_ratio <= 0 or train_ratio >= 1:
        raise ValueError("train_ratio must be between 0 and 1")
    split_index = int(len(data) * float(train_ratio))
    if split_index <= 0 or split_index >= len(data):
        raise ValueError("train_ratio produced an empty train or validation set")
    return data.slice(0, split_index), data.slice(split_index, None)


def print_data_summary(args: argparse.Namespace, data: DataFeed, train_data: DataFeed, validation_data: DataFeed) -> None:
    print("research data loaded")
    print(f"symbol={args.symbol}")
    print(f"timeframe={args.timeframe}")
    print(f"exchange={args.exchange}")
    print(f"bars={len(data)}")
    print(f"first={data.bars[0].datetime}")
    print(f"last={data.bars[-1].datetime}")
    print(f"train_bars={len(train_data)}")
    print(f"validation_bars={len(validation_data)}")


def run_candidates(
    args: argparse.Namespace,
    specs: list[CandidateSpec],
    train_data: DataFeed,
    validation_data: DataFeed,
) -> list[CandidateResult]:
    results: list[CandidateResult] = []
    for index, spec in enumerate(specs, start=1):
        train_result = run_backtest(args, spec, train_data)
        validation_result = run_backtest(args, spec, validation_data)
        train_metrics = report_to_dict(analyze(train_result, args.timeframe))
        validation_metrics = report_to_dict(analyze(validation_result, args.timeframe))
        score = score_candidate(validation_metrics)
        results.append(
            CandidateResult(
                spec=spec,
                train_result=train_result,
                validation_result=validation_result,
                train_metrics=train_metrics,
                validation_metrics=validation_metrics,
                score=score,
            )
        )
        print(
            f"[{index}/{len(specs)}] {spec.family} score={score:.4f} "
            f"validation_return={validation_metrics['total_return']} "
            f"validation_drawdown={validation_metrics['max_drawdown']} "
            f"validation_trades={validation_metrics['trade_count']}"
        )
    return results


def run_backtest(args: argparse.Namespace, spec: CandidateSpec, data: DataFeed) -> BacktestResult:
    strategy = spec.strategy_cls(**spec.params)
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=args.initial_cash,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            leverage=args.leverage,
        )
    )
    return engine.run(strategy, data)


def analyze(result: BacktestResult, timeframe: str) -> PerformanceReport:
    periods_per_year = PERIODS_PER_YEAR_5M if timeframe == "5m" else 365
    return PerformanceAnalyzer(periods_per_year=periods_per_year).analyze(result.equity_curve, result.trades)


def report_to_dict(report: PerformanceReport) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in asdict(report).items():
        result[key] = str(value) if isinstance(value, Decimal) else value
    return result


def score_candidate(metrics: dict[str, Any]) -> float:
    total_return = float(metrics["total_return"])
    max_drawdown = float(metrics["max_drawdown"])
    sharpe_ratio = float(metrics["sharpe_ratio"])
    trade_count = int(metrics["trade_count"])
    if trade_count < 4:
        return -9999.0
    return sharpe_ratio + total_return * 2 + max_drawdown


def passes_basic_filters(metrics: dict[str, Any]) -> bool:
    return (
        int(metrics["trade_count"]) >= 4
        and float(metrics["total_return"]) > 0
        and float(metrics["max_drawdown"]) > -0.3
        and Decimal(metrics["final_equity"]) > 0
    )


def print_ranked_candidates(results: list[CandidateResult]) -> None:
    print("top candidates")
    for rank, result in enumerate(results, start=1):
        metrics = result.validation_metrics
        print(
            f"#{rank} family={result.spec.family} score={result.score:.4f} "
            f"return={metrics['total_return']} drawdown={metrics['max_drawdown']} "
            f"sharpe={metrics['sharpe_ratio']:.4f} trades={metrics['trade_count']} params={result.spec.params}"
        )


def print_best_candidate(result: CandidateResult) -> None:
    print("best qualified candidate")
    print(f"family={result.spec.family}")
    print(f"params={result.spec.params}")
    print(f"score={result.score:.4f}")
    print(f"train_metrics={result.train_metrics}")
    print(f"validation_metrics={result.validation_metrics}")


def save_best_result(args: argparse.Namespace, repository: TradingRepository, data: DataFeed, best: CandidateResult):
    full_result = run_backtest(args, best.spec, data)
    full_metrics = report_to_dict(analyze(full_result, args.timeframe))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    strategy_name = best.spec.strategy_cls.name
    config = {
        "source": "research/research_runner.py",
        "research_only": True,
        "strategy_family": best.spec.family,
        "params": best.spec.params,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "exchange": args.exchange,
        "start": str(data.bars[0].datetime),
        "end": str(data.bars[-1].datetime),
        "limit": args.limit,
        "train_ratio": str(args.train_ratio),
        "train_metrics": best.train_metrics,
        "validation_metrics": best.validation_metrics,
        "full_metrics": full_metrics,
        "selection_score": best.score,
    }
    strategy = best.spec.strategy_cls(**best.spec.params)
    return repository.save_backtest_result(
        full_result,
        strategy_name=strategy_name,
        trading_mode=strategy.trading_mode.value,
        run_name=f"Research Best {args.symbol} {args.timeframe} {best.spec.family} {timestamp}",
        config=config,
        symbols=[args.symbol],
        timeframe=args.timeframe,
    )


if __name__ == "__main__":
    main()
