from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from statistics import median, stdev

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    run_momentum_topk,
)
from stephen_quant.evaluation import EvaluationError, spearman_correlation
from stephen_quant.integrity.models import TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.qmt.models import QmtDailyBar, QmtDataError
from stephen_quant.qmt.qd_membership import PointInTimeMembership

from .execution import DiscoveryExecutionConfig
from .models import FactorSchema
from .screening import ScreeningWindow

STABILITY_DIAGNOSTICS_VERSION = "v1.8.18-stability-capacity-1.0.0"


@dataclass(frozen=True)
class SliceScore:
    slice_name: str
    dates: int
    observations: int
    mean_rank_ic: float | None


@dataclass(frozen=True)
class CapacityStressRegistration:
    participation_rate: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class CapacityStressScore:
    participation_rate: float
    trial_id: str
    trial_number: int
    periods: int
    net_total_return: float
    annualized_net_sharpe: float | None
    max_drawdown: float
    total_cost: float
    capacity_clipped_notional: float
    clipped_orders: int


@dataclass(frozen=True)
class StabilityDiagnosticsReport:
    method_version: str
    schema_id: str
    fingerprint: str
    regime_lookback: int
    regimes: tuple[SliceScore, ...]
    adv_terciles: tuple[SliceScore, ...]
    capacity_stress: tuple[CapacityStressScore, ...]
    industry_neutralization: str
    validation_window_opened: bool
    test_window_opened: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("diagnostic report language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V1.8.18 稳定性与容量压力诊断" if zh else "# V1.8.18 Stability and Capacity Stress",
            "",
            f"- Factor: `{self.schema_id}`",
            f"- Fingerprint: `{self.fingerprint}`",
            f"- Prior-information regime lookback: {self.regime_lookback}",
            f"- Industry neutralization: {self.industry_neutralization}",
            f"- Validation window opened: {self.validation_window_opened}",
            f"- Final test window opened: {self.test_window_opened}",
            "",
            "## Market regimes / 市场状态",
            "",
            "| Slice | Dates | Observations | Mean RankIC |",
            "|---|---:|---:|---:|",
        ]
        lines.extend(_slice_line(item) for item in self.regimes)
        lines.extend(
            [
                "",
                "## ADV terciles / 成交容量分层",
                "",
                "| Slice | Dates | Observations | Mean RankIC |",
                "|---|---:|---:|---:|",
            ]
        )
        lines.extend(_slice_line(item) for item in self.adv_terciles)
        lines.extend(
            [
                "",
                "## Participation stress / 参与率压力",
                "",
                "| Trial | Participation | Periods | Net return | Sharpe | MDD | Cost | Capacity clipped |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in self.capacity_stress:
            sharpe = "N/A" if item.annualized_net_sharpe is None else f"{item.annualized_net_sharpe:.6f}"
            lines.append(
                f"| {item.trial_number} | {item.participation_rate:.2%} | {item.periods} | "
                f"{item.net_total_return:.2%} | {sharpe} | {item.max_drawdown:.2%} | "
                f"{item.total_cost:.2f} | {item.capacity_clipped_notional:.2f} |"
            )
        return "\n".join(lines) + "\n"


def _slice_line(item: SliceScore) -> str:
    value = "N/A" if item.mean_rank_ic is None else f"{item.mean_rank_ic:.6f}"
    return f"| `{item.slice_name}` | {item.dates} | {item.observations} | {value} |"


def point_in_time_industry_groups(
    memberships: Sequence[PointInTimeMembership],
    *,
    instruments: Sequence[str],
    decision_at: str,
) -> dict[str, str]:
    """Resolve exactly one visible industry per instrument or fail closed."""

    decision = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
    if decision.tzinfo is None:
        raise QmtDataError("industry decision_at must include a timezone")
    wanted = {instrument.upper() for instrument in instruments}
    latest: dict[str, tuple[datetime, str]] = {}
    ambiguous: set[str] = set()
    for row in memberships:
        if row.membership_kind != "industry" or row.instrument.upper() not in wanted:
            continue
        effective = datetime.fromisoformat(row.effective_at.replace("Z", "+00:00"))
        available = datetime.fromisoformat(row.available_at.replace("Z", "+00:00"))
        if effective > decision or available >= decision:
            continue
        instrument = row.instrument.upper()
        current = latest.get(instrument)
        if current is None or effective > current[0]:
            latest[instrument] = (effective, row.group_id)
            ambiguous.discard(instrument)
        elif effective == current[0] and row.group_id != current[1]:
            ambiguous.add(instrument)
    missing = wanted - set(latest)
    if missing or ambiguous:
        raise QmtDataError(
            "point-in-time industry mapping is incomplete or ambiguous: "
            f"missing={len(missing)}, ambiguous={len(ambiguous)}"
        )
    return {instrument: latest[instrument][1] for instrument in sorted(wanted)}


def register_capacity_stress_trials(
    registry: ExperimentRegistry,
    *,
    experiment_id: str,
    window: ScreeningWindow,
    participation_rates: tuple[float, ...],
    seed: int,
) -> tuple[CapacityStressRegistration, ...]:
    if not participation_rates or len(set(participation_rates)) != len(participation_rates):
        raise ValueError("capacity stress rates must be non-empty and unique")
    if any(not 0 < rate <= 1 for rate in participation_rates):
        raise ValueError("capacity stress rates must be in (0, 1]")
    registered = []
    for rate in participation_rates:
        trial_id, trial_number = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="v1.8.18_capacity_stress",
                factor_set="preregistered_flow_divergence_or_execution_winner",
                hyperparams=json.dumps(
                    {"max_participation_rate": rate}, separators=(",", ":"), sort_keys=True
                ),
                seed=seed,
                train_start=window.research_start,
                train_end=window.research_end,
                validation_start=window.validation_start,
                validation_end=window.validation_end,
                test_start=window.test_start,
                test_end=window.test_end,
            )
        )
        registered.append(CapacityStressRegistration(rate, trial_id, trial_number))
    return tuple(registered)


def _non_overlapping(
    rows: tuple[BaselineObservation, ...], horizon_sessions: int
) -> tuple[BaselineObservation, ...]:
    dates = sorted({row.execution_at for row in rows})
    selected = set(dates[::horizon_sessions])
    return tuple(row for row in rows if row.execution_at in selected)


def _mean_rank_ic(
    rows: Sequence[BaselineObservation], direction: int
) -> tuple[int, int, float | None]:
    grouped: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        if row.eligible:
            grouped[row.execution_at].append(row)
    values = []
    observations = 0
    for cross_section in grouped.values():
        if len(cross_section) < 3:
            continue
        try:
            values.append(
                spearman_correlation(
                    [direction * row.signal for row in cross_section],
                    [row.forward_return for row in cross_section],
                )
            )
        except EvaluationError:
            continue
        observations += len(cross_section)
    return len(values), observations, (sum(values) / len(values) if values else None)


def _market_regimes(
    bars: Sequence[QmtDailyBar], execution_dates: Sequence[str], lookback: int
) -> dict[str, str]:
    closes: dict[str, dict[str, float]] = defaultdict(dict)
    for bar in bars:
        closes[bar.trade_date][bar.instrument] = bar.close
    dates = sorted(closes)
    market_returns: dict[str, float] = {}
    rolling_volatility: dict[str, float] = {}
    for previous, current in pairwise(dates):
        common = set(closes[previous]) & set(closes[current])
        if common:
            market_returns[current] = sum(
                closes[current][instrument] / closes[previous][instrument] - 1
                for instrument in common
            ) / len(common)
    return_dates = sorted(market_returns)
    for index, day in enumerate(return_dates):
        history = [market_returns[item] for item in return_dates[max(0, index - lookback + 1) : index + 1]]
        if len(history) >= lookback:
            rolling_volatility[day] = stdev(history)
    result: dict[str, str] = {}
    for execution_at in sorted(set(execution_dates)):
        execution_day = execution_at[:10]
        visible_dates = [day for day in return_dates if day < execution_day]
        if len(visible_dates) < lookback:
            result[execution_at] = "insufficient_history"
            continue
        recent = visible_dates[-lookback:]
        trend = math.prod(1 + market_returns[day] for day in recent) - 1
        signal_day = recent[-1]
        visible_vol = [
            value for day, value in rolling_volatility.items() if day <= signal_day
        ]
        if not visible_vol:
            result[execution_at] = "insufficient_history"
            continue
        volatility = rolling_volatility[signal_day]
        result[execution_at] = (
            ("up" if trend >= 0 else "down")
            + "_"
            + ("high_vol" if volatility >= median(visible_vol) else "low_vol")
        )
    return result


def run_stability_diagnostics(
    registry: ExperimentRegistry,
    *,
    schema: FactorSchema,
    rows: tuple[BaselineObservation, ...],
    bars: Sequence[QmtDailyBar],
    registrations: tuple[CapacityStressRegistration, ...],
    snapshot_id: str,
    experiment_id: str,
    code_version: str,
    horizon_sessions: int,
    regime_lookback: int,
    execution_config: DiscoveryExecutionConfig,
) -> StabilityDiagnosticsReport:
    if regime_lookback < 5:
        raise ValueError("regime lookback must be at least five sessions")
    regimes_by_date = _market_regimes(
        bars, [row.execution_at for row in rows], regime_lookback
    )
    regime_rows: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        regime_rows[regimes_by_date[row.execution_at]].append(row)
    regime_scores = tuple(
        SliceScore(name, *_mean_rank_ic(group, schema.direction))
        for name, group in sorted(regime_rows.items())
    )

    bucket_rows: dict[str, list[BaselineObservation]] = defaultdict(list)
    by_date: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        if row.eligible:
            by_date[row.execution_at].append(row)
    names = ("low_adv", "mid_adv", "high_adv")
    for cross_section in by_date.values():
        ordered = sorted(cross_section, key=lambda row: (row.average_daily_value, row.instrument))
        for index, row in enumerate(ordered):
            bucket_rows[names[min(index * 3 // len(ordered), 2)]].append(row)
    bucket_scores = tuple(
        SliceScore(name, *_mean_rank_ic(bucket_rows.get(name, ()), schema.direction))
        for name in names
    )

    execution_rows = _non_overlapping(rows, horizon_sessions)
    stress_scores = []
    for item in registrations:
        report = run_momentum_topk(
            execution_rows,
            BaselineLineage(
                schema.schema_id,
                schema.version,
                snapshot_id,
                experiment_id,
                item.trial_id,
                code_version,
            ),
            BaselineConfig(
                top_k=execution_config.top_k,
                direction=schema.direction,
                commission_bps=execution_config.commission_bps,
                sell_tax_bps=execution_config.sell_tax_bps,
                slippage_bps=execution_config.slippage_bps,
                impact_coefficient_bps=execution_config.impact_coefficient_bps,
                max_participation_rate=item.participation_rate,
                periods_per_year=max(1, 252 // horizon_sessions),
                missing_holding_policy="stale_zero_return",
            ),
            initial_nav=execution_config.initial_nav,
        )
        metrics = report.metrics
        score = CapacityStressScore(
            item.participation_rate,
            item.trial_id,
            item.trial_number,
            metrics.periods,
            metrics.net_total_return,
            metrics.net_sharpe,
            metrics.max_drawdown,
            metrics.total_cost,
            metrics.capacity_clipped_notional,
            metrics.clipped_orders,
        )
        registry.record_trial_result(
            item.trial_id,
            json.dumps(asdict(score), separators=(",", ":"), sort_keys=True),
        )
        stress_scores.append(score)
    return StabilityDiagnosticsReport(
        method_version=STABILITY_DIAGNOSTICS_VERSION,
        schema_id=schema.schema_id,
        fingerprint=schema.fingerprint,
        regime_lookback=regime_lookback,
        regimes=regime_scores,
        adv_terciles=bucket_scores,
        capacity_stress=tuple(stress_scores),
        industry_neutralization="NOT_RUN_NO_POINT_IN_TIME_STOCK_INDUSTRY_MAPPING",
        validation_window_opened=False,
        test_window_opened=False,
    )
