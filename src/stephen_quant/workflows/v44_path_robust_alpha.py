from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median, stdev

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeConfig,
    QmtDailyBar,
    build_multisource_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v41_semantic_alpha import (
    UsageEvent,
    UsageSpec,
    V41Config,
    _anchors,
    classify_prior_regimes,
    evaluate_usage,
    evaluate_usage_events,
)
from .v43_conversion import FROZEN_SIGNAL_IDS, FROZEN_SIGNAL_SET_SHA256, _schemas

V44_VERSION = "v4.4-path-robust-alpha-1.0.0"
REGIMES = ("all", "risk_on", "risk_off", "mixed", "liquidity_shock")


@dataclass(frozen=True)
class V44Config:
    data_start: str = "2021-01-01"
    research_years: tuple[int, ...] = (2022, 2023)
    final_year: int = 2024
    horizon: int = 20
    universe_top_n: int = 50
    usages: tuple[str, ...] = ("BUY", "AVOID")
    breadths: tuple[int, ...] = (5, 10, 20)
    regimes: tuple[str, ...] = REGIMES
    primary_nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_median_path_sharpe: float = 0.50
    minimum_quartile_path_sharpe: float = 0.0
    minimum_positive_paths: int = 16
    minimum_final_median_path_sharpe: float = 0.50
    minimum_final_positive_paths: int = 16
    maximum_final_drawdown: float = 0.25
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if self.research_years != (2022, 2023) or self.final_year != 2024:
            raise ValueError("V4.4 windows are frozen to 2022/2023 research and 2024 final")
        if self.horizon != 20 or self.primary_nav != 3_000_000.0:
            raise ValueError("V4.4 horizon and primary NAV are frozen")
        if self.usages != ("BUY", "AVOID") or self.breadths != (5, 10, 20):
            raise ValueError("V4.4 conversion grid is frozen")
        if self.regimes != REGIMES:
            raise ValueError("V4.4 prior-only regime grid is frozen")
        if not 1 <= self.minimum_positive_paths <= self.horizon:
            raise ValueError("minimum_positive_paths must fit the offset-path count")


@dataclass(frozen=True)
class PathRobustness:
    year: int
    paths: int
    median_sharpe: float
    lower_quartile_sharpe: float
    positive_return_paths: int
    mean_path_return: float
    worst_path_return: float
    worst_path_drawdown: float
    incremental_daily_sharpe: float
    incremental_return: float
    portfolio_excess_sharpe: float
    portfolio_excess_return: float
    portfolio_drawdown: float


@dataclass(frozen=True)
class RobustCandidate:
    candidate_id: str
    usage: str
    breadth: int
    regime: str
    research: tuple[PathRobustness, ...]
    eligible: bool
    trial_id: str
    trial_number: int

    @property
    def identity(self) -> str:
        return f"{self.candidate_id}:{self.usage.lower()}_breadth{self.breadth}_{self.regime}"


@dataclass(frozen=True)
class V44Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    frozen_signal_set_sha256: str
    search_trials: int
    selected: RobustCandidate
    final: PathRobustness
    recorded_trial_count: int
    dsr_probability: float
    signal_placebo_p: float
    return_placebo_p: float
    final_window_opened_once: bool
    decision: str
    failures: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.4 路径稳健 Alpha 报告" if zh else "# V4.4 Path-Robust Alpha Report",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选' if zh else 'Candidate'}: `{self.selected.identity}`",
            f"- {'搜索 Trials' if zh else 'Search trials'}: {self.search_trials}",
            f"- {'全局记录 Trials' if zh else 'Global recorded trials'}: {self.recorded_trial_count}",
            f"- DSR: {self.dsr_probability:.6f}",
            (
                f"- {'信号/收益置换 p' if zh else 'Signal/return placebo p'}: "
                f"{self.signal_placebo_p:.6f} / {self.return_placebo_p:.6f}"
            ),
            "",
            (
                "| Window | Median path Sharpe | Q25 path Sharpe | Positive paths | "
                "Mean path return | Incremental return | Portfolio excess return | Drawdown |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in (*self.selected.research, self.final):
            lines.append(
                f"| {item.year} | {item.median_sharpe:.4f} | {item.lower_quartile_sharpe:.4f} | "
                f"{item.positive_return_paths}/{item.paths} | {item.mean_path_return:.2%} | "
                f"{item.incremental_return:.2%} | {item.portfolio_excess_return:.2%} | "
                f"{item.portfolio_drawdown:.2%} |"
            )
        lines.extend(
            [
                "",
                (
                    f"- {'失败门禁' if zh else 'Failed gates'}: "
                    f"{', '.join(self.failures) or ('无' if zh else 'none')}"
                ),
                "",
                (
                    "说明：路径指标来自 20 条互不重叠的持有期偏移路径；增量收益扣除了同状态、同现金暴露的等权对照。"
                    if zh
                    else "Path metrics use 20 non-overlapping holding-period offsets; incremental returns subtract an equal-weight control with the same regime and cash exposure."
                ),
                "",
            ]
        )
        return "\n".join(lines)


def _quartile(values: list[float]) -> float:
    if not values:
        raise ValueError("quartile requires values")
    ordered = sorted(values)
    return ordered[math.floor(0.25 * (len(ordered) - 1))]


def summarize_paths(
    year: int,
    candidate_events: tuple[UsageEvent, ...],
    control_events: tuple[UsageEvent, ...],
    *,
    horizon: int,
    portfolio_sharpe: float,
    portfolio_return: float,
    portfolio_drawdown: float,
) -> PathRobustness:
    candidate = {(item.offset, item.day): item.excess_return for item in candidate_events}
    control = {(item.offset, item.day): item.excess_return for item in control_events}
    if set(candidate) != set(control):
        raise ValueError("candidate and control event grids differ")
    path_sharpes: list[float] = []
    path_returns: list[float] = []
    path_drawdowns: list[float] = []
    all_incremental: list[float] = []
    for offset in range(horizon):
        returns = [
            (candidate[key] - control[key]) * horizon
            for key in sorted(candidate)
            if key[0] == offset
        ]
        if len(returns) < 3:
            raise ValueError(f"offset path {offset} has fewer than three observations")
        deviation = stdev(returns)
        path_sharpes.append(
            mean(returns) / deviation * math.sqrt(252 / horizon) if deviation > 0 else 0.0
        )
        path_returns.append(math.prod(1 + item for item in returns) - 1)
        wealth = 1.0
        peak = 1.0
        drawdown = 0.0
        for item in returns:
            wealth *= 1 + item
            peak = max(peak, wealth)
            drawdown = min(drawdown, wealth / peak - 1)
        path_drawdowns.append(drawdown)
        all_incremental.extend((candidate[key] - control[key]) for key in sorted(candidate) if key[0] == offset)
    ordered_incremental = [candidate[key] - control[key] for key in sorted(candidate, key=lambda x: (x[1], x[0]))]
    deviation = stdev(ordered_incremental)
    return PathRobustness(
        year,
        len(path_sharpes),
        median(path_sharpes),
        _quartile(path_sharpes),
        sum(item > 0 for item in path_returns),
        mean(path_returns),
        min(path_returns),
        min(path_drawdowns),
        mean(ordered_incremental) / deviation * math.sqrt(252) if deviation > 0 else 0.0,
        math.prod(1 + item for item in ordered_incremental) - 1,
        portfolio_sharpe,
        portfolio_return,
        portfolio_drawdown,
    )


def research_eligible(metrics: tuple[PathRobustness, ...], config: V44Config) -> bool:
    return len(metrics) == 2 and all(
        item.median_sharpe >= config.minimum_median_path_sharpe
        and item.lower_quartile_sharpe > config.minimum_quartile_path_sharpe
        and item.positive_return_paths >= config.minimum_positive_paths
        and item.mean_path_return > 0
        and item.incremental_return > 0
        and item.portfolio_excess_return > 0
        for item in metrics
    )


def select_robust_candidate(candidates: tuple[RobustCandidate, ...]) -> RobustCandidate:
    eligible = [item for item in candidates if item.eligible]
    if not eligible:
        raise ValueError("no candidate passed the frozen 2022/2023 path-stability gate")
    return max(
        eligible,
        key=lambda item: (
            min(metric.lower_quartile_sharpe for metric in item.research),
            min(metric.median_sharpe for metric in item.research),
            min(metric.mean_path_return for metric in item.research),
            -item.breadth,
            item.identity,
        ),
    )


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    *,
    stage: str,
    factor_set: str,
    parameters: dict[str, object],
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            stage,
            factor_set,
            json.dumps(parameters, sort_keys=True, separators=(",", ":")),
            seed,
            "2022-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
            "2025-01-01",
            "2026-12-31",
        )
    )


def _build_panel(
    schema,
    *,
    year: int,
    bars: tuple[QmtDailyBar, ...],
    alternatives: dict[str, tuple],
    anchors: tuple,
) -> tuple[EvaluationObservation, ...]:
    built = build_multisource_factor_observations(bars, alternatives, schema.compile(), anchors)
    return tuple(
        EvaluationObservation(
            timestamp=row.execution_at,
            instrument=row.instrument,
            factor_value=schema.direction * row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon="20d",
            subperiod=str(year),
            regime="unspecified",
        )
        for row in built
        if row.eligible and row.execution_at.startswith(f"{year}-")
    )


def run_v44_path_robust_alpha(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    chip_dir: str | Path,
    limit_event_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V44Config | None = None,
    prior_inferential_trials: int = 841,
) -> V44Report:
    config = config or V44Config()
    config.validate()
    if prior_inferential_trials < 0:
        raise ValueError("prior_inferential_trials cannot be negative")
    schemas = _schemas()
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    memberships = {day: members for day, members in memberships.items() if day <= "2024-12-31"}
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    daily_files = select_qd_daily_files(root, start_date=config.data_start, end_date="2024-12-31")
    daily_manifest = build_selected_files_snapshot_manifest(root, daily_files)
    daily = load_qd_daily_directory(
        root, start_date=config.data_start, end_date="2024-12-31", instruments=instruments
    )
    alternatives = {}
    alternative_hashes = {}
    for kind, source in (("chip", chip_dir), ("limit_event", limit_event_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date="2022-01-01",
                end_date="2024-12-31",
                ingested_at=config.ingested_at,
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        alternative_hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {"qd_daily": daily_manifest.snapshot_sha256, "dynamic_universe": membership_sha, **alternative_hashes}
    )
    snapshot_id = registry.register_snapshot(
        composite, vendor_version=V44_VERSION, notes="2022/2023 research; frozen 2024 one-shot final"
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.4 path-robust alpha search",
            "Non-overlapping path stability and regime-matched controls may isolate a real stock-selection effect.",
            snapshot_id,
            code_version,
            json.dumps({"version": V44_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    usage_config = V41Config(
        primary_nav=config.primary_nav,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_bps=config.impact_bps,
        participation_rate=config.participation_rate,
        ingested_at=config.ingested_at,
    )
    regimes = classify_prior_regimes(
        calendar=calendar, bars=by_instrument, execution_members=execution_members, config=usage_config
    )
    panels: dict[tuple[int, str], tuple[EvaluationObservation, ...]] = {}
    for year in (*config.research_years, config.final_year):
        anchors = _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=by_instrument,
            execution_members=execution_members,
        )
        for candidate_id, schema in schemas.items():
            required = {
                source: alternatives[source.removeprefix("qd_")]
                for source in schema.data_sources
                if source != "qd_daily"
            }
            panels[(year, candidate_id)] = _build_panel(
                schema, year=year, bars=daily.bars, alternatives=required, anchors=anchors
            )
    candidates: list[RobustCandidate] = []
    trial_sharpes: list[float] = []
    for candidate_id in FROZEN_SIGNAL_IDS:
        for usage in config.usages:
            for breadth in config.breadths:
                for regime in config.regimes:
                    spec = UsageSpec(usage, breadth, regime)
                    trial = _trial(
                        registry,
                        experiment_id,
                        stage="v4.4_2022_2023_path_search",
                        factor_set=f"{candidate_id}:{spec.identity}",
                        parameters={"candidate_id": candidate_id, "spec": asdict(spec)},
                        seed=config.seed,
                    )
                    yearly: list[PathRobustness] = []
                    for year in config.research_years:
                        rows = panels[(year, candidate_id)]
                        candidate_events, _ = evaluate_usage_events(
                            rows, rows, spec, horizon=config.horizon, nav=config.primary_nav,
                            bars=by_instrument, calendar=calendar, regimes=regimes, config=usage_config,
                        )
                        control_events, _ = evaluate_usage_events(
                            rows, rows, UsageSpec("AVOID", 0, regime), horizon=config.horizon,
                            nav=config.primary_nav, bars=by_instrument, calendar=calendar,
                            regimes=regimes, config=usage_config,
                        )
                        portfolio, _ = evaluate_usage(
                            candidate_id, rows, rows, spec, year=year, horizon=config.horizon,
                            nav=config.primary_nav, bars=by_instrument, calendar=calendar,
                            regimes=regimes, config=usage_config,
                        )
                        yearly.append(
                            summarize_paths(
                                year, candidate_events, control_events, horizon=config.horizon,
                                portfolio_sharpe=portfolio.excess_sharpe,
                                portfolio_return=portfolio.cumulative_excess_return,
                                portfolio_drawdown=portfolio.maximum_drawdown,
                            )
                        )
                    robust = RobustCandidate(
                        candidate_id, usage, breadth, regime, tuple(yearly),
                        research_eligible(tuple(yearly), config), trial[0], trial[1],
                    )
                    registry.record_trial_result(trial[0], json.dumps(asdict(robust), sort_keys=True))
                    candidates.append(robust)
                    trial_sharpes.append(
                        min(item.median_sharpe for item in yearly) / math.sqrt(252 / config.horizon)
                    )
    selected = select_robust_candidate(tuple(candidates))
    selected_raw = min(item.median_sharpe for item in selected.research) / math.sqrt(
        252 / config.horizon
    )
    recorded_before_final = prior_inferential_trials + registry.global_trial_count()
    dsr = deflated_sharpe_ratio(
        observed_sharpe=selected_raw,
        trial_sharpes=trial_sharpes,
        recorded_trial_count=recorded_before_final,
        observations=24,
    )
    final_trial = _trial(
        registry,
        experiment_id,
        stage="v4.4_2024_frozen_final",
        factor_set=selected.identity,
        parameters={"frozen_from": selected.trial_id, "year": config.final_year},
        seed=config.seed,
    )
    final_spec = UsageSpec(selected.usage, selected.breadth, selected.regime)
    final_rows = panels[(config.final_year, selected.candidate_id)]
    final_events, _ = evaluate_usage_events(
        final_rows, final_rows, final_spec, horizon=config.horizon, nav=config.primary_nav,
        bars=by_instrument, calendar=calendar, regimes=regimes, config=usage_config,
    )
    final_controls, _ = evaluate_usage_events(
        final_rows, final_rows, UsageSpec("AVOID", 0, selected.regime), horizon=config.horizon,
        nav=config.primary_nav, bars=by_instrument, calendar=calendar, regimes=regimes,
        config=usage_config,
    )
    final_portfolio, _ = evaluate_usage(
        selected.candidate_id, final_rows, final_rows, final_spec, year=config.final_year,
        horizon=config.horizon, nav=config.primary_nav, bars=by_instrument, calendar=calendar,
        regimes=regimes, config=usage_config,
    )
    final = summarize_paths(
        config.final_year, final_events, final_controls, horizon=config.horizon,
        portfolio_sharpe=final_portfolio.excess_sharpe,
        portfolio_return=final_portfolio.cumulative_excess_return,
        portfolio_drawdown=final_portfolio.maximum_drawdown,
    )
    registry.record_trial_result(final_trial[0], json.dumps(asdict(final), sort_keys=True))
    regime_rows = tuple(
        row for row in final_rows
        if selected.regime == "all" or regimes.get(row.timestamp[:10]) is not None
        and regimes[row.timestamp[:10]].state == selected.regime
    )
    signal_placebo = run_placebo(
        regime_rows, horizon="20d", direction=1, method="signal_shuffle", seed=config.seed,
        repetitions=config.placebo_repetitions, min_cross_section=10,
    )
    return_placebo = run_placebo(
        regime_rows, horizon="20d", direction=1, method="return_permutation", seed=config.seed,
        repetitions=config.placebo_repetitions, min_cross_section=10,
    )
    failures = []
    if final.median_sharpe < config.minimum_final_median_path_sharpe:
        failures.append("final_median_path_sharpe")
    if final.lower_quartile_sharpe <= config.minimum_quartile_path_sharpe:
        failures.append("final_quartile_path_sharpe")
    if final.positive_return_paths < config.minimum_final_positive_paths:
        failures.append("final_positive_paths")
    if final.incremental_return <= 0 or final.mean_path_return <= 0:
        failures.append("final_incremental_return")
    if final.portfolio_excess_return <= 0:
        failures.append("final_portfolio_excess_return")
    if final.portfolio_drawdown < -config.maximum_final_drawdown:
        failures.append("final_drawdown")
    if dsr.probability < config.minimum_dsr:
        failures.append("multiplicity_dsr")
    if signal_placebo.empirical_p_value > config.maximum_placebo_p:
        failures.append("signal_placebo")
    if return_placebo.empirical_p_value > config.maximum_placebo_p:
        failures.append("return_placebo")
    report = V44Report(
        V44_VERSION, experiment_id, snapshot_id, composite.snapshot_sha256,
        FROZEN_SIGNAL_SET_SHA256, len(candidates), selected, final,
        prior_inferential_trials + registry.global_trial_count(), dsr.probability,
        signal_placebo.empirical_p_value, return_placebo.empirical_p_value, True,
        "PASS_ALPHA_COURT" if not failures else "REJECT_ALPHA_COURT", tuple(failures),
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.4-path-robust-alpha.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.4-path-robust-alpha.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.4-path-robust-alpha.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
