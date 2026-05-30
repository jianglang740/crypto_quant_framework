from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from typing import Any

from crypto_quant.strategy.base import StrategyBase

from research.candidate_strategies import ResearchLiquiditySweepReclaimStrategy, ResearchVolatilitySqueezeBreakoutStrategy


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    family: str
    strategy_cls: type[StrategyBase]
    params: dict[str, Any]


SQUEEZE_BREAKOUT_SPACE = {
    "breakout_window": [24, 36, 48],
    "range_window": [8, 12, 18],
    "compression_ratio": [Decimal("0.5"), Decimal("0.65"), Decimal("0.8")],
    "breakout_buffer": [Decimal("0.0005"), Decimal("0.001"), Decimal("0.0015")],
    "volume_window": [18, 24, 36],
    "volume_multiplier": [Decimal("1.0"), Decimal("1.2"), Decimal("1.5")],
    "position_ratio": [Decimal("0.05"), Decimal("0.08")],
    "stop_loss_rate": [Decimal("0.008"), Decimal("0.012")],
    "take_profit_rate": [Decimal("0.012"), Decimal("0.018"), Decimal("0.024")],
    "max_bars_in_position": [24, 36],
    "cooldown_bars": [3, 6],
}

LIQUIDITY_SWEEP_SPACE = {
    "sweep_window": [24, 48, 72],
    "sweep_buffer": [Decimal("0.0005"), Decimal("0.001"), Decimal("0.0015")],
    "reclaim_buffer": [Decimal("0"), Decimal("0.0005"), Decimal("0.001")],
    "min_lower_wick_ratio": [Decimal("0.35"), Decimal("0.45"), Decimal("0.55")],
    "volume_window": [18, 24, 36],
    "volume_multiplier": [Decimal("1.0"), Decimal("1.1"), Decimal("1.3")],
    "position_ratio": [Decimal("0.05"), Decimal("0.08")],
    "stop_loss_rate": [Decimal("0.006"), Decimal("0.008"), Decimal("0.012")],
    "take_profit_rate": [Decimal("0.008"), Decimal("0.012"), Decimal("0.018")],
    "max_bars_in_position": [18, 24, 36],
    "cooldown_bars": [3, 6],
}


def build_search_space(strategy_family: str | None = None, max_runs: int | None = None) -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    selected_family = strategy_family.lower() if strategy_family else None

    if selected_family in (None, "squeeze", "squeeze_breakout", "volatility_squeeze"):
        specs.extend(_build_specs("volatility_squeeze_breakout", ResearchVolatilitySqueezeBreakoutStrategy, SQUEEZE_BREAKOUT_SPACE))
    if selected_family in (None, "sweep", "liquidity_sweep", "liquidity_reclaim"):
        specs.extend(_build_specs("liquidity_sweep_reclaim", ResearchLiquiditySweepReclaimStrategy, LIQUIDITY_SWEEP_SPACE))

    if max_runs is not None:
        return specs[:max_runs]
    return specs


def _build_specs(family: str, strategy_cls: type[StrategyBase], space: dict[str, list[Any]]) -> list[CandidateSpec]:
    keys = list(space)
    return [
        CandidateSpec(
            family=family,
            strategy_cls=strategy_cls,
            params=dict(zip(keys, values, strict=True)),
        )
        for values in product(*(space[key] for key in keys))
    ]
