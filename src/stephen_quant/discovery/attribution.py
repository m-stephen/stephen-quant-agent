from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime

from stephen_quant.baseline import BaselineObservation
from stephen_quant.evaluation import EvaluationError, ols_residuals, spearman_correlation
from stephen_quant.integrity.models import TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry

from .models import FactorSchema
from .screening import ScreeningWindow

FACTOR_ATTRIBUTION_VERSION = "v1.8.20-factor-attribution-1.0.0"


@dataclass(frozen=True)
class AttributionThresholds:
    minimum_residual_rank_ic: float = 0.02
    minimum_monotonicity: float = 0.50
    maximum_date_concentration: float = 0.50
    minimum_execution_sharpe: float = 0.50
    maximum_drawdown: float = 0.25

    def validate(self) -> None:
        values = asdict(self)
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("attribution thresholds must be finite")
        if not -1 <= self.minimum_residual_rank_ic <= 1:
            raise ValueError("minimum residual RankIC must be in [-1, 1]")
        if not -1 <= self.minimum_monotonicity <= 1:
            raise ValueError("minimum monotonicity must be in [-1, 1]")
        if not 0 <= self.maximum_date_concentration <= 1:
            raise ValueError("maximum date concentration must be in [0, 1]")
        if self.minimum_execution_sharpe < 0:
            raise ValueError("minimum execution Sharpe must be non-negative")
        if not 0 <= self.maximum_drawdown <= 1:
            raise ValueError("maximum drawdown must be in [0, 1]")


@dataclass(frozen=True)
class AttributionRegistration:
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class QuantileReturn:
    quantile: int
    dates: int
    observations: int
    mean_forward_return: float


@dataclass(frozen=True)
class FactorAttributionReport:
    method_version: str
    trial_id: str
    trial_number: int
    schema_id: str
    fingerprint: str
    control_schema_ids: tuple[str, ...]
    dates: int
    observations: int
    raw_rank_ic: float
    residual_rank_ic: float
    quantile_returns: tuple[QuantileReturn, ...]
    quantile_monotonicity: float
    long_leg_return: float
    short_leg_return: float
    long_short_spread: float
    top_decile_absolute_date_contribution_share: float
    execution_net_return: float
    execution_sharpe: float | None
    execution_max_drawdown: float
    failure_labels: tuple[str, ...]
    recommendation: str
    validation_window_opened: bool
    test_window_opened: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("attribution report language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V1.8.20 因子增量价值与收益归因" if zh else "# V1.8.20 Factor Incremental Value and Return Attribution",
            "",
            f"- Factor: `{self.schema_id}`",
            f"- Controls: {', '.join(f'`{item}`' for item in self.control_schema_ids)} + `log_adv`",
            f"- Dates / 日期: {self.dates}",
            f"- Observations / 观测: {self.observations}",
            f"- Raw RankIC / 原始 RankIC: {self.raw_rank_ic:.6f}",
            f"- Residual RankIC / 残差 RankIC: {self.residual_rank_ic:.6f}",
            f"- Quantile monotonicity / 分位单调性: {self.quantile_monotonicity:.6f}",
            f"- Long leg / 多头端: {self.long_leg_return:.4%}",
            f"- Short leg / 空头端: {self.short_leg_return:.4%}",
            f"- Long-short spread / 多空差: {self.long_short_spread:.4%}",
            f"- Top 10% absolute date contribution / 极端日期集中度: {self.top_decile_absolute_date_contribution_share:.2%}",
            f"- Execution net return / 执行净收益: {self.execution_net_return:.2%}",
            f"- Execution Sharpe: {self.execution_sharpe}",
            f"- Execution MDD / 最大回撤: {self.execution_max_drawdown:.2%}",
            f"- Failure labels / 失败标签: {', '.join(self.failure_labels) or 'NONE'}",
            f"- Recommendation / 建议: **{self.recommendation}**",
            f"- Validation window opened: {self.validation_window_opened}",
            f"- Final test window opened: {self.test_window_opened}",
            "",
            "## Quantile returns / 分位收益",
            "",
            "| Quantile | Dates | Observations | Mean forward return |",
            "|---:|---:|---:|---:|",
        ]
        lines.extend(
            f"| {item.quantile} | {item.dates} | {item.observations} | {item.mean_forward_return:.4%} |"
            for item in self.quantile_returns
        )
        return "\n".join(lines) + "\n"


def register_attribution_trial(
    registry: ExperimentRegistry,
    *,
    experiment_id: str,
    window: ScreeningWindow,
    target: FactorSchema,
    controls: Sequence[FactorSchema],
    thresholds: AttributionThresholds,
    seed: int,
) -> AttributionRegistration:
    thresholds.validate()
    if not controls:
        raise ValueError("factor attribution requires at least one control")
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v1.8.20_factor_incremental_attribution",
            factor_set=target.schema_id,
            hyperparams=json.dumps(
                {
                    "control_schema_ids": [item.schema_id for item in controls],
                    "residual_controls": ["intercept", "factor_controls", "log_adv"],
                    "thresholds": asdict(thresholds),
                },
                separators=(",", ":"),
                sort_keys=True,
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
    return AttributionRegistration(trial_id, trial_number)


def _visible(row: BaselineObservation) -> bool:
    execution = datetime.fromisoformat(row.execution_at.replace("Z", "+00:00"))
    signal = datetime.fromisoformat(row.signal_available_at.replace("Z", "+00:00"))
    liquidity = datetime.fromisoformat(row.liquidity_available_at.replace("Z", "+00:00"))
    return signal < execution and liquidity < execution


def _mean_rank_ic(signal_and_return: Sequence[tuple[list[float], list[float]]]) -> float:
    values = []
    for signals, returns in signal_and_return:
        try:
            values.append(spearman_correlation(signals, returns))
        except EvaluationError:
            continue
    if not values:
        raise ValueError("factor attribution has no valid RankIC cross-sections")
    return sum(values) / len(values)


def run_factor_attribution(
    registry: ExperimentRegistry,
    *,
    registration: AttributionRegistration,
    target_schema: FactorSchema,
    target_rows: tuple[BaselineObservation, ...],
    controls: Sequence[tuple[FactorSchema, tuple[BaselineObservation, ...]]],
    thresholds: AttributionThresholds,
    execution_net_return: float,
    execution_sharpe: float | None,
    execution_max_drawdown: float,
    quantiles: int = 10,
) -> FactorAttributionReport:
    thresholds.validate()
    if quantiles < 3:
        raise ValueError("factor attribution requires at least three quantiles")
    target = {
        (row.execution_at, row.instrument): row
        for row in target_rows
        if row.eligible
    }
    if not target or any(not _visible(row) for row in target.values()):
        raise ValueError("target attribution panel is empty or not point-in-time visible")
    control_maps = []
    for schema, rows in controls:
        panel = {(row.execution_at, row.instrument): row for row in rows if row.eligible}
        missing = set(target) - set(panel)
        if missing:
            raise ValueError(
                f"control panel {schema.schema_id} is missing {len(missing)} target observations"
            )
        if any(not _visible(panel[key]) for key in target):
            raise ValueError(f"control panel {schema.schema_id} is not point-in-time visible")
        control_maps.append((schema, panel))

    by_date: dict[str, list[tuple[str, BaselineObservation]]] = defaultdict(list)
    for (execution_at, instrument), row in target.items():
        by_date[execution_at].append((instrument, row))

    raw_panels = []
    residual_panels = []
    bucket_daily: dict[int, list[float]] = defaultdict(list)
    bucket_observations: dict[int, int] = defaultdict(int)
    daily_spreads = []
    used_observations = 0
    used_dates = 0
    for execution_at, cross_section in sorted(by_date.items()):
        if len(cross_section) < quantiles:
            continue
        ordered = sorted(cross_section, key=lambda item: item[0])
        oriented = [target_schema.direction * row.signal for _, row in ordered]
        returns = [row.forward_return for _, row in ordered]
        control_values = []
        for instrument, row in ordered:
            key = (execution_at, instrument)
            values = [schema.direction * panel[key].signal for schema, panel in control_maps]
            values.append(math.log(row.average_daily_value))
            control_values.append(values)
            if any(panel[key].forward_return != row.forward_return for _, panel in control_maps):
                raise ValueError("control and target panels have inconsistent forward returns")
        residual = ols_residuals(oriented, control_values)
        raw_panels.append((oriented, returns))
        residual_panels.append((residual, returns))

        ranked = sorted(zip(oriented, returns, strict=True), key=lambda item: item[0])
        daily_returns: dict[int, list[float]] = defaultdict(list)
        for index, (_, forward_return) in enumerate(ranked):
            bucket = min(index * quantiles // len(ranked), quantiles - 1) + 1
            daily_returns[bucket].append(forward_return)
            bucket_observations[bucket] += 1
        if set(daily_returns) != set(range(1, quantiles + 1)):
            continue
        means = {bucket: sum(values) / len(values) for bucket, values in daily_returns.items()}
        for bucket, value in means.items():
            bucket_daily[bucket].append(value)
        daily_spreads.append(means[quantiles] - means[1])
        used_observations += len(ordered)
        used_dates += 1

    if used_dates == 0:
        raise ValueError("factor attribution has no complete quantile cross-sections")
    quantile_returns = tuple(
        QuantileReturn(
            bucket,
            len(bucket_daily[bucket]),
            bucket_observations[bucket],
            sum(bucket_daily[bucket]) / len(bucket_daily[bucket]),
        )
        for bucket in range(1, quantiles + 1)
    )
    quantile_means = [item.mean_forward_return for item in quantile_returns]
    monotonicity = spearman_correlation(list(range(1, quantiles + 1)), quantile_means)
    absolute = sorted((abs(value) for value in daily_spreads), reverse=True)
    tail_count = max(1, math.ceil(len(absolute) * 0.10))
    concentration = sum(absolute[:tail_count]) / sum(absolute) if sum(absolute) else 0.0

    raw_rank_ic = _mean_rank_ic(raw_panels)
    residual_rank_ic = _mean_rank_ic(residual_panels)
    long_leg = quantile_means[-1]
    short_leg = quantile_means[0]
    labels = []
    if residual_rank_ic < thresholds.minimum_residual_rank_ic:
        labels.append("NO_INCREMENTAL_INFORMATION")
    if monotonicity < thresholds.minimum_monotonicity:
        labels.append("WEAK_MONOTONICITY")
    if long_leg <= 0:
        labels.append("WEAK_LONG_LEG")
    if concentration > thresholds.maximum_date_concentration:
        labels.append("DATE_CONCENTRATION")
    if execution_sharpe is None or execution_sharpe < thresholds.minimum_execution_sharpe:
        labels.append("LOW_EXECUTION_SHARPE")
    if execution_max_drawdown < -thresholds.maximum_drawdown:
        labels.append("EXCESSIVE_DRAWDOWN")
    critical = {"NO_INCREMENTAL_INFORMATION", "LOW_EXECUTION_SHARPE", "EXCESSIVE_DRAWDOWN"}
    recommendation = (
        "STOP_OR_REDESIGN" if critical.intersection(labels) else "CONTINUE_CONSTRAINED"
    )
    report = FactorAttributionReport(
        method_version=FACTOR_ATTRIBUTION_VERSION,
        trial_id=registration.trial_id,
        trial_number=registration.trial_number,
        schema_id=target_schema.schema_id,
        fingerprint=target_schema.fingerprint,
        control_schema_ids=tuple(schema.schema_id for schema, _ in controls),
        dates=used_dates,
        observations=used_observations,
        raw_rank_ic=raw_rank_ic,
        residual_rank_ic=residual_rank_ic,
        quantile_returns=quantile_returns,
        quantile_monotonicity=monotonicity,
        long_leg_return=long_leg,
        short_leg_return=short_leg,
        long_short_spread=long_leg - short_leg,
        top_decile_absolute_date_contribution_share=concentration,
        execution_net_return=execution_net_return,
        execution_sharpe=execution_sharpe,
        execution_max_drawdown=execution_max_drawdown,
        failure_labels=tuple(labels),
        recommendation=recommendation,
        validation_window_opened=False,
        test_window_opened=False,
    )
    registry.record_trial_result(
        registration.trial_id,
        json.dumps(asdict(report), separators=(",", ":"), sort_keys=True),
    )
    return report
