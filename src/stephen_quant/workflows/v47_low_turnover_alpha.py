from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean, stdev

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
from .v41_semantic_alpha import UsageEvent, UsageSpec, V41Config, _anchors, evaluate_usage_events
from .v44_path_robust_alpha import PathRobustness, summarize_paths
from .v46_orthogonal_search import YEARS, _ensemble_panel, curated_schemas

V47_VERSION = "v4.7-low-turnover-alpha-1.0.0"
SIGNAL_STRUCTURES = ("flow_only", "flow_auction_ensemble")
BUFFER_RANKS = (0, 5, 10)
COST_MULTIPLIERS = (1.0, 2.0)
FLOW_SCHEMA_ID = "flow_price_divergence_5_20d"
AUCTION_SCHEMA_ID = "auction_strength_5_20d"


@dataclass(frozen=True)
class V47Config:
    data_start: str = "2021-01-01"
    years: tuple[int, ...] = YEARS
    universe_top_n: int = 50
    horizon: int = 20
    breadth: int = 10
    primary_nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_positive_paths: int = 16
    minimum_positive_years: int = 3
    minimum_median_path_sharpe: float = 0.0
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if self.years != YEARS or self.horizon != 20 or self.breadth != 10:
            raise ValueError("V4.7 time grid and breadth are frozen")
        if self.primary_nav != 3_000_000.0:
            raise ValueError("V4.7 primary NAV is frozen at CNY 3 million")
        if len(SIGNAL_STRUCTURES) * len(BUFFER_RANKS) * len(COST_MULTIPLIERS) != 12:
            raise AssertionError("V4.7 must contain exactly 12 predeclared Trials")


@dataclass(frozen=True)
class TurnoverAttribution:
    mean_turnover: float
    total_cost_rate: float
    gross_portfolio_excess_return: float
    net_portfolio_excess_return: float


@dataclass(frozen=True)
class BufferedAvoidAccountingEvent:
    """Auditable components of one staggered 20-session cohort contribution."""

    day: str
    end_day: str
    offset: int
    gross_portfolio_return: float
    benchmark_return: float
    net_portfolio_return: float
    excess_return: float
    turnover: float
    cost_rate: float
    selected_instruments: int
    retained_instruments: int


@dataclass(frozen=True)
class GridEvidence:
    signal_structure: str
    buffer_ranks: int
    cost_multiplier: float
    combined: PathRobustness
    years: tuple[PathRobustness, ...]
    attribution: TurnoverAttribution
    capacity_clipped_notional: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V47Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    grid_trials: int
    grid: tuple[GridEvidence, ...]
    selected_signal_structure: str | None
    selected_buffer_ranks: int | None
    standard: GridEvidence | None
    double_cost: GridEvidence | None
    signal_placebo_p: float | None
    return_placebo_p: float | None
    dsr_probability: float | None
    dsr_sharpe_estimates_used: int
    recorded_trial_count: int
    development_decision: str
    alpha_court_decision: str
    development_failures: tuple[str, ...]
    court_failures: tuple[str, ...]
    evidence_status: str
    forward_shadow_start: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.7 低换手 Alpha 转换" if zh else "# V4.7 Low-Turnover Alpha Conversion",
            "",
            f"**{'开发结论' if zh else 'Development decision'}: `{self.development_decision}`**",
            f"**Alpha Court: `{self.alpha_court_decision}`**",
            "",
            f"- {'预声明 Trials' if zh else 'Predeclared Trials'}: {self.grid_trials}",
            f"- {'选中结构' if zh else 'Selected structure'}: {self.selected_signal_structure or 'N/A'}",
            f"- {'持仓缓冲' if zh else 'Holding buffer'}: {self.selected_buffer_ranks}",
            f"- DSR: {self.dsr_probability if self.dsr_probability is not None else 'N/A'}",
            f"- {'DSR 夏普样本' if zh else 'DSR Sharpe estimates'}: {self.dsr_sharpe_estimates_used}",
            f"- {'证据级别' if zh else 'Evidence status'}: {self.evidence_status}",
            "",
            "| Cost | Full excess | Full Sharpe | Increment | Increment Sharpe | Positive paths | Median / Q25 | Turnover |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for label, item in (("1x", self.standard), ("2x", self.double_cost)):
            if item is None:
                continue
            path = item.combined
            lines.append(
                f"| {label} | {path.portfolio_excess_return:.2%} | "
                f"{path.portfolio_excess_sharpe:.4f} | {path.incremental_return:.2%} | "
                f"{path.incremental_daily_sharpe:.4f} | {path.positive_return_paths}/20 | "
                f"{path.median_sharpe:.4f} / {path.lower_quartile_sharpe:.4f} | "
                f"{item.attribution.mean_turnover:.4%} |"
            )
        lines.extend(
            [
                "",
                (
                    f"- {'置换 p 值（信号/收益）' if zh else 'Placebo p-values (signal/return)'}: "
                    f"{self.signal_placebo_p} / {self.return_placebo_p}"
                ),
                (
                    f"- {'开发门禁失败' if zh else 'Development failures'}: "
                    f"{', '.join(self.development_failures) or ('无' if zh else 'none')}"
                ),
                (
                    f"- {'Court 失败' if zh else 'Court failures'}: "
                    f"{', '.join(self.court_failures) or ('无' if zh else 'none')}"
                ),
                f"- {'前向 Shadow 起始' if zh else 'Forward shadow start'}: {self.forward_shadow_start}",
                "",
                (
                    "说明：2022–2025 均为重复使用的开发证据。即使开发门禁通过，也不能替代独立前向验证。"
                    if zh
                    else "Note: 2022-2025 is reused development evidence. Passing the development gate cannot replace independent forward validation."
                ),
                "",
            ]
        )
        return "\n".join(lines)


def _selected_schemas():
    schemas = {schema.schema_id: schema for _, schema in curated_schemas()}
    try:
        return schemas[FLOW_SCHEMA_ID], schemas[AUCTION_SCHEMA_ID]
    except KeyError as exc:
        raise ValueError(f"missing frozen V4.7 schema: {exc.args[0]}") from exc


def _drawdown(returns: list[float]) -> float:
    wealth = peak = 1.0
    worst = 0.0
    for value in returns:
        wealth *= 1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1)
    return worst


def _portfolio_metrics(events: tuple[UsageEvent, ...]) -> tuple[float, float, float]:
    returns = [item.excess_return for item in sorted(events, key=lambda item: (item.day, item.offset))]
    if not returns:
        return 0.0, 0.0, 0.0
    deviation = stdev(returns) if len(returns) > 1 else 0.0
    sharpe = mean(returns) / deviation * math.sqrt(252) if deviation > 0 else 0.0
    return sharpe, math.prod(1 + value for value in returns) - 1, _drawdown(returns)


def evaluate_buffered_avoid_accounting_events(
    rows: tuple[EvaluationObservation, ...],
    *,
    breadth: int,
    buffer_ranks: int,
    horizon: int,
    nav: float,
    bars: dict[str, dict[str, QmtDailyBar]],
    calendar: tuple[str, ...],
    config: V41Config,
) -> tuple[tuple[BufferedAvoidAccountingEvent, ...], float]:
    """Execute an AVOID signal and retain the absolute-return accounting components."""
    if breadth <= 0 or buffer_ranks < 0 or buffer_ranks > breadth:
        raise ValueError("invalid V4.7 breadth or buffer")
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    positions = {day: index for index, day in enumerate(calendar)}
    dates = sorted(grouped)
    round_trip_cost = (
        config.commission_bps * 2
        + config.sell_tax_bps
        + config.slippage_bps * 2
        + config.impact_bps * 2
    ) / 10_000
    events: list[BufferedAvoidAccountingEvent] = []
    clipped = 0.0
    for offset in range(horizon):
        previous: dict[str, float] = {}
        for day in dates[offset::horizon]:
            cross = sorted(grouped[day], key=lambda item: (item.factor_value, item.instrument))
            if len(cross) <= breadth or day not in positions or positions[day] == 0:
                continue
            rank = {item.instrument: index for index, item in enumerate(cross)}
            target_count = len(cross) - breadth
            exit_rank = max(0, breadth - buffer_ranks)
            kept = [
                item
                for item in cross
                if item.instrument in previous and rank[item.instrument] >= exit_rank
            ]
            kept.sort(key=lambda item: (-rank[item.instrument], item.instrument))
            selected = kept[:target_count]
            retained_instruments = len(selected)
            selected_ids = {item.instrument for item in selected}
            for item in reversed(cross):
                if len(selected) >= target_count:
                    break
                if item.instrument not in selected_ids:
                    selected.append(item)
                    selected_ids.add(item.instrument)
            raw_weight = 1 / target_count
            executed: dict[str, float] = {}
            prior_day = calendar[positions[day] - 1]
            by_id = {item.instrument: item for item in cross}
            for item in selected:
                series = bars.get(item.instrument, {})
                capacity = series[prior_day].amount * config.participation_rate if prior_day in series else 0.0
                desired = nav / horizon * raw_weight
                actual = min(desired, capacity)
                clipped += desired - actual
                executed[item.instrument] = actual / nav
            turnover = 0.5 * sum(
                abs(executed.get(name, 0.0) - previous.get(name, 0.0))
                for name in set(executed) | set(previous)
            )
            cost = turnover * round_trip_cost
            benchmark = mean(item.forward_return for item in cross) / horizon
            portfolio_return = sum(
                weight * by_id[instrument].forward_return
                for instrument, weight in executed.items()
                if instrument in by_id
            )
            end_days = {item.label_end_at[:10] for item in selected}
            if len(end_days) != 1:
                raise ValueError("buffered cohort has inconsistent label end dates")
            net_return = portfolio_return - cost
            events.append(
                BufferedAvoidAccountingEvent(
                    day=day,
                    end_day=end_days.pop(),
                    offset=offset,
                    gross_portfolio_return=portfolio_return,
                    benchmark_return=benchmark,
                    net_portfolio_return=net_return,
                    excess_return=net_return - benchmark,
                    turnover=turnover,
                    cost_rate=cost,
                    selected_instruments=len(selected),
                    retained_instruments=retained_instruments,
                )
            )
            previous = executed
    return tuple(sorted(events, key=lambda item: (item.day, item.offset))), clipped


def evaluate_buffered_avoid_events(
    rows: tuple[EvaluationObservation, ...],
    *,
    breadth: int,
    buffer_ranks: int,
    horizon: int,
    nav: float,
    bars: dict[str, dict[str, QmtDailyBar]],
    calendar: tuple[str, ...],
    config: V41Config,
) -> tuple[tuple[UsageEvent, ...], float]:
    """Execute an AVOID signal with a rank buffer, independently for each offset path."""
    accounting, clipped = evaluate_buffered_avoid_accounting_events(
        rows,
        breadth=breadth,
        buffer_ranks=buffer_ranks,
        horizon=horizon,
        nav=nav,
        bars=bars,
        calendar=calendar,
        config=config,
    )
    return (
        tuple(
            UsageEvent(
                item.day,
                item.offset,
                item.excess_return,
                item.turnover,
                item.cost_rate,
                True,
            )
            for item in accounting
        ),
        clipped,
    )


def _path(
    year: int,
    events: tuple[UsageEvent, ...],
    controls: tuple[UsageEvent, ...],
    horizon: int,
) -> PathRobustness:
    sharpe, total_return, drawdown = _portfolio_metrics(events)
    return summarize_paths(
        year,
        events,
        controls,
        horizon=horizon,
        portfolio_sharpe=sharpe,
        portfolio_return=total_return,
        portfolio_drawdown=drawdown,
    )


def _development_failures(
    standard: GridEvidence,
    double: GridEvidence,
    *,
    signal_p: float,
    return_p: float,
    config: V47Config,
) -> tuple[str, ...]:
    failures = []
    for label, item in (("standard", standard), ("double_cost", double)):
        path = item.combined
        if path.portfolio_excess_return <= 0 or path.incremental_return <= 0:
            failures.append(f"{label}_return")
        if path.positive_return_paths < config.minimum_positive_paths:
            failures.append(f"{label}_path_count")
        if path.median_sharpe < config.minimum_median_path_sharpe:
            failures.append(f"{label}_median_path_sharpe")
        positive_years = sum(
            year.portfolio_excess_return > 0 and year.incremental_return > 0
            for year in item.years
        )
        if positive_years < config.minimum_positive_years or item.years[-1].incremental_return <= 0:
            failures.append(f"{label}_cross_year")
    if signal_p > config.maximum_placebo_p:
        failures.append("signal_placebo")
    if return_p > config.maximum_placebo_p:
        failures.append("return_placebo")
    return tuple(failures)


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    *,
    structure: str,
    buffer_ranks: int,
    cost_multiplier: float,
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            "v4.7_predeclared_low_turnover_grid",
            structure,
            json.dumps(
                {"buffer_ranks": buffer_ranks, "cost_multiplier": cost_multiplier},
                sort_keys=True,
                separators=(",", ":"),
            ),
            seed,
            "2022-01-01",
            "2024-12-31",
            "2025-01-01",
            "2025-12-31",
            "2026-08-19",
            "2027-08-18",
        )
    )


def v46_trial_sharpes(prior_registry: ExperimentRegistry) -> tuple[float, ...]:
    """Recover the exact 40-estimate V4.6 DSR reference distribution from its ledger."""
    values = []
    with prior_registry.connect() as conn:
        rows = conn.execute(
            "SELECT model_name, result_json FROM trials ORDER BY created_at, trial_number"
        ).fetchall()
    for row in rows:
        stage = str(row[0])
        if not stage.startswith("v4.6_") or row[1] is None:
            continue
        result = json.loads(str(row[1]))
        if stage == "v4.6_nested_candidate_development":
            years = result.get("years")
            if not isinstance(years, list) or len(years) != 4:
                raise ValueError("invalid V4.6 candidate result in prior registry")
            sharpe = mean(float(item["path"]["incremental_daily_sharpe"]) for item in years)
        elif stage == "v4.6_ensemble_stress":
            sharpe = float(result["path"]["incremental_daily_sharpe"])
        else:
            continue
        values.append(sharpe / math.sqrt(252))
    if len(values) != 40:
        raise ValueError(f"V4.7 requires the complete 40-Trial V4.6 DSR reference; found {len(values)}")
    return tuple(values)


def run_v47_low_turnover_alpha(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    registry: ExperimentRegistry,
    prior_registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V47Config | None = None,
    prior_inferential_trials: int = 1089,
) -> V47Report:
    config = config or V47Config()
    config.validate()
    prior_sharpes = v46_trial_sharpes(prior_registry)
    flow_schema, auction_schema = _selected_schemas()
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date="2025-12-31")
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily = load_qd_daily_directory(
        root, start_date=config.data_start, end_date="2025-12-31", instruments=instruments
    )
    alternatives = {}
    alternative_hashes = {}
    for kind, source in (("auction", auction_dir), ("fund_flow", fund_flow_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.data_start,
                end_date="2025-12-31",
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
        composite,
        vendor_version=V47_VERSION,
        notes="2022-2025 reused development evidence; 2026 sealed from tuning",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.7 low-turnover alpha conversion",
            "A fixed holding buffer may preserve flow-divergence information under doubled costs.",
            snapshot_id,
            code_version,
            json.dumps({"version": V47_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    anchors = tuple(
        row
        for year in YEARS
        for row in _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=bars,
            execution_members=execution_members,
        )
    )
    panels = {}
    for schema, source_kind in ((flow_schema, "fund_flow"), (auction_schema, "auction")):
        built = build_multisource_factor_observations(
            daily.bars,
            {f"qd_{source_kind}": alternatives[source_kind]},
            schema.compile(),
            anchors,
        )
        panels[schema.schema_id] = tuple(
            EvaluationObservation(
                timestamp=row.execution_at,
                instrument=row.instrument,
                factor_value=schema.direction * row.signal,
                factor_available_at=row.signal_available_at,
                label_start_at=row.execution_at,
                label_end_at=row.return_end_at,
                forward_return=row.forward_return,
                horizon="20d",
                subperiod=row.execution_at[:4],
                regime="unspecified",
            )
            for row in built
            if row.eligible
        )
    structures = {
        "flow_only": panels[FLOW_SCHEMA_ID],
        "flow_auction_ensemble": tuple(
            row
            for year in YEARS
            for row in _ensemble_panel(
                (
                    tuple(item for item in panels[FLOW_SCHEMA_ID] if item.timestamp.startswith(f"{year}-")),
                    tuple(item for item in panels[AUCTION_SCHEMA_ID] if item.timestamp.startswith(f"{year}-")),
                ),
                year=year,
            )
        ),
    }
    base_usage = V41Config(
        primary_nav=config.primary_nav,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_bps=config.impact_bps,
        participation_rate=config.participation_rate,
        ingested_at=config.ingested_at,
    )
    grid = []
    raw_sharpes = []
    for structure in SIGNAL_STRUCTURES:
        rows = structures[structure]
        for buffer_ranks in BUFFER_RANKS:
            for multiplier in COST_MULTIPLIERS:
                usage = replace(
                    base_usage,
                    commission_bps=config.commission_bps * multiplier,
                    sell_tax_bps=config.sell_tax_bps * multiplier,
                    slippage_bps=config.slippage_bps * multiplier,
                    impact_bps=config.impact_bps * multiplier,
                )
                events, clipped = evaluate_buffered_avoid_events(
                    rows,
                    breadth=config.breadth,
                    buffer_ranks=buffer_ranks,
                    horizon=config.horizon,
                    nav=config.primary_nav,
                    bars=bars,
                    calendar=calendar,
                    config=usage,
                )
                controls, _ = evaluate_usage_events(
                    rows,
                    rows,
                    UsageSpec("AVOID", 0, "all"),
                    horizon=config.horizon,
                    nav=config.primary_nav,
                    bars=bars,
                    calendar=calendar,
                    regimes={},
                    config=usage,
                )
                combined = _path(2022, events, controls, config.horizon)
                years = tuple(
                    _path(
                        year,
                        tuple(item for item in events if item.day.startswith(f"{year}-")),
                        tuple(item for item in controls if item.day.startswith(f"{year}-")),
                        config.horizon,
                    )
                    for year in YEARS
                )
                total_cost = sum(item.cost_rate for item in events)
                net_returns = [item.excess_return for item in events]
                gross_returns = [item.excess_return + item.cost_rate for item in events]
                attribution = TurnoverAttribution(
                    mean(item.turnover for item in events),
                    total_cost,
                    math.prod(1 + item for item in gross_returns) - 1,
                    math.prod(1 + item for item in net_returns) - 1,
                )
                trial = _trial(
                    registry,
                    experiment_id,
                    structure=structure,
                    buffer_ranks=buffer_ranks,
                    cost_multiplier=multiplier,
                    seed=config.seed,
                )
                item = GridEvidence(
                    structure,
                    buffer_ranks,
                    multiplier,
                    combined,
                    years,
                    attribution,
                    clipped,
                    trial[0],
                    trial[1],
                )
                registry.record_trial_result(trial[0], json.dumps(asdict(item), sort_keys=True))
                grid.append(item)
                raw_sharpes.append(combined.incremental_daily_sharpe / math.sqrt(252))
    if len(grid) != 12 or registry.global_trial_count() != 12:
        raise AssertionError("V4.7 trial ledger must contain exactly 12 Trials")
    paired = []
    for structure in SIGNAL_STRUCTURES:
        for buffer_ranks in BUFFER_RANKS:
            standard = next(
                item for item in grid
                if item.signal_structure == structure
                and item.buffer_ranks == buffer_ranks
                and item.cost_multiplier == 1.0
            )
            double = next(
                item for item in grid
                if item.signal_structure == structure
                and item.buffer_ranks == buffer_ranks
                and item.cost_multiplier == 2.0
            )
            paired.append((standard, double))
    selected_standard, selected_double = max(
        paired,
        key=lambda pair: (
            min(pair[0].combined.portfolio_excess_return, pair[1].combined.portfolio_excess_return),
            min(pair[0].combined.positive_return_paths, pair[1].combined.positive_return_paths),
            min(pair[0].combined.median_sharpe, pair[1].combined.median_sharpe),
            -pair[1].attribution.mean_turnover,
            pair[0].signal_structure,
            pair[0].buffer_ranks,
        ),
    )
    selected_rows = structures[selected_standard.signal_structure]
    signal_p = run_placebo(
        selected_rows,
        horizon="20d",
        direction=1,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    ).empirical_p_value
    return_p = run_placebo(
        selected_rows,
        horizon="20d",
        direction=1,
        method="return_permutation",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    ).empirical_p_value
    recorded = prior_inferential_trials + registry.global_trial_count()
    dsr_values = [*prior_sharpes, *raw_sharpes]
    dsr = deflated_sharpe_ratio(
        observed_sharpe=selected_standard.combined.incremental_daily_sharpe / math.sqrt(252),
        trial_sharpes=dsr_values,
        recorded_trial_count=recorded,
        observations=len({item.timestamp[:10] for item in selected_rows}),
    ).probability
    development_failures = _development_failures(
        selected_standard,
        selected_double,
        signal_p=signal_p,
        return_p=return_p,
        config=config,
    )
    court_failures = list(development_failures)
    if dsr < config.minimum_dsr:
        court_failures.append("multiplicity_dsr")
    report = V47Report(
        V47_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        len(grid),
        tuple(grid),
        selected_standard.signal_structure,
        selected_standard.buffer_ranks,
        selected_standard,
        selected_double,
        signal_p,
        return_p,
        dsr,
        len(dsr_values),
        recorded,
        "WORTH_FORWARD_VALIDATION" if not development_failures else "NO_DEVELOPMENT_ALPHA",
        "PASS" if not court_failures else "REJECT",
        development_failures,
        tuple(court_failures),
        "2022-2025 reused development evidence; not independent final proof",
        "2026-08-19",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.7-low-turnover-alpha.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.7-low-turnover-alpha.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.7-low-turnover-alpha.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
