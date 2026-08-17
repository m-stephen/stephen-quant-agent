from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    run_momentum_topk,
)
from stephen_quant.integrity.models import TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry

from .attribution import _residuals
from .models import FactorSchema
from .screening import ScreeningWindow

PORTFOLIO_USAGE_VERSION = "v1.8.21-preregistered-portfolio-usage-1.0.0"
REFERENCE_PORTFOLIO_VERSION = "research-reference-portfolio-1.0.0"


@dataclass(frozen=True)
class PortfolioMapping:
    name: str
    ranking_policy: str
    fraction: float
    bottom_underweight: float = 0.25
    residualize_controls: bool = False

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("portfolio mapping name cannot be empty")
        if self.ranking_policy not in {
            "all_eligible",
            "top_fraction",
            "exclude_bottom_fraction",
            "bottom_fraction_underweight",
        }:
            raise ValueError("unsupported portfolio mapping policy")
        if self.ranking_policy == "all_eligible" and self.fraction != 0:
            raise ValueError("all-eligible benchmark requires zero fraction")
        if self.ranking_policy != "all_eligible" and not 0 < self.fraction < 1:
            raise ValueError("portfolio mapping fraction must be in (0, 1)")
        if not 0 <= self.bottom_underweight <= 1:
            raise ValueError("portfolio mapping underweight must be in [0, 1]")


@dataclass(frozen=True)
class PortfolioUsageConfig:
    mappings: tuple[PortfolioMapping, ...]
    initial_navs: tuple[float, ...]
    reference_mapping: str
    benchmark_mapping: str
    reference_nav: float
    horizon_sessions: int = 20
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_coefficient_bps: float = 10.0
    max_participation_rate: float = 0.05
    periods_per_year: int = 12

    def validate(self) -> None:
        if not self.mappings:
            raise ValueError("portfolio usage mappings cannot be empty")
        for item in self.mappings:
            item.validate()
        names = tuple(item.name for item in self.mappings)
        if len(set(names)) != len(names):
            raise ValueError("portfolio usage mapping names must be unique")
        if self.reference_mapping not in names:
            raise ValueError("reference mapping must be preregistered")
        if self.benchmark_mapping not in names:
            raise ValueError("benchmark mapping must be preregistered")
        if not self.initial_navs or len(set(self.initial_navs)) != len(self.initial_navs):
            raise ValueError("portfolio usage NAVs must be non-empty and unique")
        if any(not math.isfinite(value) or value <= 0 for value in self.initial_navs):
            raise ValueError("portfolio usage NAVs must be finite and positive")
        if self.reference_nav not in self.initial_navs:
            raise ValueError("reference NAV must be preregistered")
        if self.horizon_sessions < 1 or self.periods_per_year < 1:
            raise ValueError("portfolio usage periods must be positive")
        if not 0 < self.max_participation_rate <= 1:
            raise ValueError("portfolio usage participation rate must be in (0, 1]")
        if any(
            not math.isfinite(value) or value < 0
            for value in (
                self.commission_bps,
                self.sell_tax_bps,
                self.slippage_bps,
                self.impact_coefficient_bps,
            )
        ):
            raise ValueError("portfolio usage costs must be finite and non-negative")

    @property
    def manifest_sha256(self) -> str:
        self.validate()
        payload = json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class PortfolioUsageRegistration:
    mapping_name: str
    initial_nav: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class PortfolioUsageScore:
    mapping_name: str
    initial_nav: float
    trial_id: str
    trial_number: int
    periods: int
    net_total_return: float
    annualized_net_sharpe: float | None
    max_drawdown: float
    total_turnover: float
    total_cost: float
    capacity_clipped_notional: float
    tail_loss_5pct: float
    incremental_net_return: float
    incremental_net_sharpe: float | None
    incremental_max_drawdown: float


@dataclass(frozen=True)
class ReferencePortfolio:
    version: str
    mapping_name: str
    initial_nav: float
    config_manifest_sha256: str
    research_only: bool


@dataclass(frozen=True)
class PortfolioUsageReport:
    method_version: str
    config_manifest_sha256: str
    experiment_id: str
    snapshot_id: str
    target_schema_id: str
    control_schema_ids: tuple[str, ...]
    scores: tuple[PortfolioUsageScore, ...]
    reference_portfolio: ReferencePortfolio
    research_only: bool
    validation_window_opened: bool
    test_window_opened: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("portfolio usage report language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V1.8.21 预注册组合使用报告" if zh else "# V1.8.21 Preregistered Portfolio Usage Report",
            "",
            f"- {'研究属性' if zh else 'Research status'}: `research_only`",
            f"- {'目标因子' if zh else 'Target factor'}: `{self.target_schema_id}`",
            f"- {'配置哈希' if zh else 'Config hash'}: `{self.config_manifest_sha256}`",
            f"- {'参考组合' if zh else 'Reference portfolio'}: `{self.reference_portfolio.mapping_name}` @ CNY {self.reference_portfolio.initial_nav:,.0f}",
            f"- {'验证期是否打开' if zh else 'Validation opened'}: {self.validation_window_opened}",
            f"- {'最终测试期是否打开' if zh else 'Final test opened'}: {self.test_window_opened}",
            "",
            "| Mapping | NAV | Net return | Net Sharpe | Max drawdown | Δ return | Δ Sharpe | Turnover | Tail 5% |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for score in self.scores:
            sharpe = "N/A" if score.annualized_net_sharpe is None else f"{score.annualized_net_sharpe:.4f}"
            lines.append(
                f"| {score.mapping_name} | {score.initial_nav:,.0f} | "
                f"{score.net_total_return:.2%} | {sharpe} | {score.max_drawdown:.2%} | "
                f"{score.incremental_net_return:.2%} | "
                f"{'N/A' if score.incremental_net_sharpe is None else f'{score.incremental_net_sharpe:.4f}'} | "
                f"{score.total_turnover:.4f} | {score.tail_loss_5pct:.2%} |"
            )
        lines.extend(
            [
                "",
                (
                    "> 本报告使用已消耗的 2022–2024 研究数据，不构成新的样本外证据。"
                    if zh
                    else "> This report uses consumed 2022–2024 research data and is not fresh out-of-sample evidence."
                ),
            ]
        )
        return "\n".join(lines) + "\n"


def frozen_portfolio_usage_config() -> PortfolioUsageConfig:
    return PortfolioUsageConfig(
        mappings=(
            PortfolioMapping("all_eligible_benchmark", "all_eligible", 0.0),
            PortfolioMapping("top_decile", "top_fraction", 0.10),
            PortfolioMapping("top_30_percent", "top_fraction", 0.30),
            PortfolioMapping("exclude_bottom_decile", "exclude_bottom_fraction", 0.10),
            PortfolioMapping(
                "bottom_decile_underweight", "bottom_fraction_underweight", 0.10, 0.25
            ),
            PortfolioMapping(
                "risk_controlled_exclude_bottom_decile",
                "exclude_bottom_fraction",
                0.10,
                residualize_controls=True,
            ),
        ),
        initial_navs=(
            1_000_000.0,
            3_000_000.0,
            5_000_000.0,
            10_000_000.0,
            20_000_000.0,
        ),
        reference_mapping="exclude_bottom_decile",
        benchmark_mapping="all_eligible_benchmark",
        reference_nav=3_000_000.0,
    )


def register_portfolio_usage_trials(
    registry: ExperimentRegistry,
    *,
    experiment_id: str,
    window: ScreeningWindow,
    target: FactorSchema,
    config: PortfolioUsageConfig,
    seed: int,
) -> tuple[PortfolioUsageRegistration, ...]:
    config.validate()
    registrations = []
    for mapping in config.mappings:
        for initial_nav in config.initial_navs:
            trial_id, trial_number = registry.create_trial(
                TrialSpec(
                    experiment_id=experiment_id,
                    model_name="v1.8.21_preregistered_portfolio_usage",
                    factor_set=target.schema_id,
                    hyperparams=json.dumps(
                        {
                            "mapping": asdict(mapping),
                            "initial_nav": initial_nav,
                            "config_manifest_sha256": config.manifest_sha256,
                            "research_only": True,
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
            registrations.append(
                PortfolioUsageRegistration(
                    mapping.name, initial_nav, trial_id, trial_number
                )
            )
    return tuple(registrations)


def _visible(row: BaselineObservation) -> bool:
    execution = datetime.fromisoformat(row.execution_at.replace("Z", "+00:00"))
    return all(
        datetime.fromisoformat(value.replace("Z", "+00:00")) < execution
        for value in (row.signal_available_at, row.liquidity_available_at)
    )


def _residualized_rows(
    target_rows: tuple[BaselineObservation, ...],
    control_rows: Sequence[tuple[BaselineObservation, ...]],
) -> tuple[BaselineObservation, ...]:
    target = {(row.execution_at, row.instrument): row for row in target_rows if row.eligible}
    controls = [
        {(row.execution_at, row.instrument): row for row in panel if row.eligible}
        for panel in control_rows
    ]
    if not target or any(set(target) - set(panel) for panel in controls):
        raise ValueError("portfolio controls do not cover the target panel")
    if any(not _visible(row) for row in target.values()) or any(
        not _visible(panel[key]) for panel in controls for key in target
    ):
        raise ValueError("portfolio usage panel is not point-in-time visible")
    grouped: dict[str, list[tuple[str, BaselineObservation]]] = defaultdict(list)
    for (execution_at, instrument), row in target.items():
        grouped[execution_at].append((instrument, row))
    replacements: dict[tuple[str, str], float] = {}
    for execution_at, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: item[0])
        values = [row.signal for _, row in ordered]
        design = [
            [
                *(panel[(execution_at, instrument)].signal for panel in controls),
                math.log(row.average_daily_value),
            ]
            for instrument, row in ordered
        ]
        residuals = _residuals(values, design)
        replacements.update(
            ((execution_at, instrument), value)
            for (instrument, _), value in zip(ordered, residuals, strict=True)
        )
    return tuple(
        replace(row, signal=replacements[(row.execution_at, row.instrument)])
        if row.eligible
        else row
        for row in target_rows
    )


def _non_overlapping(
    rows: tuple[BaselineObservation, ...], horizon_sessions: int
) -> tuple[BaselineObservation, ...]:
    dates = sorted({row.execution_at for row in rows if row.eligible})
    selected = set(dates[::horizon_sessions])
    if not selected:
        raise ValueError("portfolio usage has no eligible execution dates")
    return tuple(row for row in rows if row.execution_at in selected)


def _tail_loss(period_returns: list[float]) -> float:
    ordered = sorted(period_returns)
    count = max(1, math.ceil(len(ordered) * 0.05))
    return sum(ordered[:count]) / count


def run_portfolio_usage(
    registry: ExperimentRegistry,
    *,
    registrations: tuple[PortfolioUsageRegistration, ...],
    target_schema: FactorSchema,
    target_rows: tuple[BaselineObservation, ...],
    control_schemas: tuple[FactorSchema, ...],
    control_rows: Sequence[tuple[BaselineObservation, ...]],
    snapshot_id: str,
    experiment_id: str,
    code_version: str,
    config: PortfolioUsageConfig,
) -> PortfolioUsageReport:
    config.validate()
    expected = len(config.mappings) * len(config.initial_navs)
    if len(registrations) != expected:
        raise ValueError("portfolio usage registrations do not match frozen workload")
    by_key = {(item.mapping_name, item.initial_nav): item for item in registrations}
    if len(by_key) != expected:
        raise ValueError("portfolio usage registrations are duplicated")
    if any(not _visible(row) for row in target_rows if row.eligible):
        raise ValueError("portfolio usage target is not point-in-time visible")
    residualized = _residualized_rows(target_rows, control_rows) if control_rows else None
    raw_reports = {}
    for mapping in config.mappings:
        if mapping.residualize_controls and residualized is None:
            raise ValueError("risk-controlled mapping requires control panels")
        rows = residualized if mapping.residualize_controls else target_rows
        assert rows is not None
        execution_rows = _non_overlapping(rows, config.horizon_sessions)
        for initial_nav in config.initial_navs:
            registration = by_key[(mapping.name, initial_nav)]
            report = run_momentum_topk(
                execution_rows,
                BaselineLineage(
                    target_schema.schema_id,
                    target_schema.version,
                    snapshot_id,
                    experiment_id,
                    registration.trial_id,
                    code_version,
                ),
                BaselineConfig(
                    top_k=1,
                    direction=target_schema.direction,
                    commission_bps=config.commission_bps,
                    sell_tax_bps=config.sell_tax_bps,
                    slippage_bps=config.slippage_bps,
                    impact_coefficient_bps=config.impact_coefficient_bps,
                    max_participation_rate=config.max_participation_rate,
                    periods_per_year=config.periods_per_year,
                    missing_holding_policy="stale_zero_return",
                    ranking_policy=mapping.ranking_policy,
                    selection_fraction=mapping.fraction,
                    bottom_underweight=mapping.bottom_underweight,
                ),
                initial_nav=initial_nav,
            )
            raw_reports[(mapping.name, initial_nav)] = (registration, report)
    scores = []
    for mapping in config.mappings:
        for initial_nav in config.initial_navs:
            registration, report = raw_reports[(mapping.name, initial_nav)]
            _, benchmark = raw_reports[(config.benchmark_mapping, initial_nav)]
            score = PortfolioUsageScore(
                mapping.name,
                initial_nav,
                registration.trial_id,
                registration.trial_number,
                report.metrics.periods,
                report.metrics.net_total_return,
                report.metrics.net_sharpe,
                report.metrics.max_drawdown,
                report.metrics.total_turnover,
                report.metrics.total_cost,
                report.metrics.capacity_clipped_notional,
                _tail_loss([item.net_return for item in report.periods]),
                report.metrics.net_total_return - benchmark.metrics.net_total_return,
                (
                    None
                    if report.metrics.net_sharpe is None or benchmark.metrics.net_sharpe is None
                    else report.metrics.net_sharpe - benchmark.metrics.net_sharpe
                ),
                report.metrics.max_drawdown - benchmark.metrics.max_drawdown,
            )
            registry.record_trial_result(
                registration.trial_id,
                json.dumps(asdict(score), separators=(",", ":"), sort_keys=True),
            )
            scores.append(score)
    return PortfolioUsageReport(
        method_version=PORTFOLIO_USAGE_VERSION,
        config_manifest_sha256=config.manifest_sha256,
        experiment_id=experiment_id,
        snapshot_id=snapshot_id,
        target_schema_id=target_schema.schema_id,
        control_schema_ids=tuple(item.schema_id for item in control_schemas),
        scores=tuple(scores),
        reference_portfolio=ReferencePortfolio(
            REFERENCE_PORTFOLIO_VERSION,
            config.reference_mapping,
            config.reference_nav,
            config.manifest_sha256,
            True,
        ),
        research_only=True,
        validation_window_opened=False,
        test_window_opened=False,
    )
