from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from stephen_quant.discovery import FactorSchema
from stephen_quant.evaluation import EvaluationObservation
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
    UsageSpec,
    V41Config,
    _anchors,
    _daily_metrics,
    economic_shape,
    evaluate_usage,
    evaluate_usage_events,
)
from .v44_path_robust_alpha import summarize_paths
from .v46_orthogonal_search import _quarterly
from .v53_independent_search import independent_schemas

V54_VERSION = "v5.4-alpha-conversion-diagnostics-1.0.1"
YEARS = (2022, 2023, 2024)
DIAGNOSTIC_IDS = (
    "limit_up_seal_strength_5_20_20d_negative",
    "auction_price_absorption_5_20_20d_positive",
    "margin_crowding_reversal_20_20_20d_negative",
)
DIAGNOSTIC_HORIZONS = (1, 5, 10, 20)
DIAGNOSTIC_BREADTHS = (20, 50, 100)
STRESS_SCENARIOS = ("standard", "double", "conservative")


@dataclass(frozen=True)
class V54Config:
    data_start: str = "2021-01-01"
    data_end: str = "2024-12-31"
    nav: float = 3_000_000.0
    diagnostic_horizons: tuple[int, ...] = DIAGNOSTIC_HORIZONS
    diagnostic_breadths: tuple[int, ...] = DIAGNOSTIC_BREADTHS
    generated_breadth: int = 50
    minimum_positive_path_fraction: float = 0.60
    ingested_at: str = "2026-08-19T00:00:00+08:00"
    seed: int = 54

    def validate(self) -> None:
        if (self.data_start, self.data_end) != ("2021-01-01", "2024-12-31"):
            raise ValueError("V5.4 data window is frozen")
        if self.nav != 3_000_000.0:
            raise ValueError("V5.4 NAV is frozen at CNY 3m")
        if self.diagnostic_horizons != DIAGNOSTIC_HORIZONS:
            raise ValueError("V5.4 diagnostic horizons are frozen")
        if self.diagnostic_breadths != DIAGNOSTIC_BREADTHS:
            raise ValueError("V5.4 diagnostic breadths are frozen")
        if self.generated_breadth != 50 or self.minimum_positive_path_fraction != 0.60:
            raise ValueError("V5.4 generated-candidate gates are frozen")


@dataclass(frozen=True)
class AnnualConversion:
    year: int
    dates: int
    observations: int
    rank_ic: float
    top_bottom: float
    gross_excess_return: float
    net_excess_return: float
    net_excess_sharpe: float
    gross_to_net_drag: float
    mean_turnover: float
    total_cost_rate: float
    active_days: int
    positive_paths: int
    paths: int
    quantile_monotonicity: float | None
    minimum_cross_section: int
    mean_cross_section: float
    capacity_clipped_notional: float


@dataclass(frozen=True)
class ConversionCell:
    candidate_id: str
    domain: str
    horizon: int
    breadth: int
    years: tuple[AnnualConversion, ...]
    compounded_gross_excess: float
    compounded_net_excess: float
    gross_to_net_drag: float
    cost_tolerance_multiplier: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class GeneratedCandidate:
    candidate_id: str
    fingerprint: str
    domain: str
    direction: int
    horizon: int
    formula: str
    years: tuple[AnnualConversion, ...]
    stable: bool
    decay_alarm: bool
    objective: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class GeneratedStress:
    candidate_id: str
    domain: str
    scenario: str
    compounded_net_excess: float
    minimum_positive_paths: int
    capacity_clipped_notional: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V54Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    diagnostic_trials: int
    conversion_cells: tuple[ConversionCell, ...]
    best_conversion_cell: ConversionCell
    diagnostic_conclusion: str
    generated_trials: int
    generated_candidates: tuple[GeneratedCandidate, ...]
    stable_candidates: int
    selected_candidates: tuple[GeneratedCandidate, ...]
    validation_trials: int
    stresses: tuple[GeneratedStress, ...]
    prior_inferential_trials: int
    recorded_trial_count: int
    decision: str
    failures: tuple[str, ...]
    evidence_status: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        best = self.best_conversion_cell
        lines = [
            "# V5.4 Alpha 转化诊断与受约束生成" if zh else "# V5.4 Alpha Conversion Diagnostics and Constrained Generation",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'诊断 Trials' if zh else 'Diagnostic Trials'}: {self.diagnostic_trials}",
            f"- {'生成 Trials' if zh else 'Generated Trials'}: {self.generated_trials}",
            f"- {'验证 Trials' if zh else 'Validation Trials'}: {self.validation_trials}",
            f"- {'累计 Trials' if zh else 'Cumulative Trials'}: {self.recorded_trial_count}",
            "",
            "## 最佳固定公式转换单元" if zh else "## Best fixed-formula conversion cell",
            "",
            f"- Candidate: `{best.candidate_id}`",
            f"- Horizon / breadth: {best.horizon} / {best.breadth}",
            f"- Gross / net: {best.compounded_gross_excess:.2%} / {best.compounded_net_excess:.2%}",
            f"- Cost tolerance: {best.cost_tolerance_multiplier:.2f}x standard cost",
            f"- {'诊断判断' if zh else 'Diagnostic conclusion'}: {self.diagnostic_conclusion}",
            "",
            "## 受约束生成结果" if zh else "## Constrained-generation result",
            "",
            "| Candidate | Domain | Horizon | 2022 net | 2023 net | 2024 net | Stable |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for item in self.generated_candidates:
            annual = {row.year: row.net_excess_return for row in item.years}
            lines.append(
                f"| `{item.candidate_id}` | {item.domain} | {item.horizon} | "
                f"{annual[2022]:.2%} | {annual[2023]:.2%} | {annual[2024]:.2%} | {item.stable} |"
            )
        lines.extend(
            [
                "",
                f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.failures) or 'none'}",
                f"- {'证据状态' if zh else 'Evidence status'}: {self.evidence_status}",
                "",
            ]
        )
        return "\n".join(lines)


def constrained_schemas() -> tuple[tuple[str, FactorSchema], ...]:
    templates = (
        (
            "margin",
            "margin_net_demand_intensity_5",
            "margin_net_demand",
            "(mean(margin_financing_buy, 5) - mean(margin_financing_repay, 5)) / (mean(amount, 5) + 1.0)",
            ("qd_daily", "qd_margin"),
            ("amount", "margin_financing_buy", "margin_financing_repay"),
            20,
        ),
        (
            "margin",
            "margin_balance_price_divergence_20",
            "margin_balance_price_divergence",
            "period_return(margin_financing_balance, 20) - period_return(close, 20)",
            ("qd_daily", "qd_margin"),
            ("close", "margin_financing_balance"),
            20,
        ),
        (
            "auction",
            "auction_liquidity_pressure_5",
            "auction_liquidity_pressure",
            "mean(auction_return, 5) * mean(auction_volume_ratio_1, 5)",
            ("qd_auction",),
            ("auction_return", "auction_volume_ratio_1"),
            5,
        ),
        (
            "auction",
            "auction_amount_absorption_5",
            "auction_amount_absorption",
            "(mean(auction_amount, 5) / (mean(amount, 5) + 1.0)) * (0.0 - period_return(close, 5))",
            ("qd_daily", "qd_auction"),
            ("amount", "auction_amount", "close"),
            5,
        ),
        (
            "limit_event",
            "limit_seal_retention_5",
            "limit_seal_retention",
            "mean(kpl_close_seal_amount, 5) / (mean(kpl_max_seal_amount, 5) + 1.0)",
            ("qd_limit_event",),
            ("kpl_close_seal_amount", "kpl_max_seal_amount"),
            5,
        ),
        (
            "limit_event",
            "limit_main_flow_to_float_cap_5",
            "limit_main_flow_to_float_cap",
            "mean(kpl_main_net_amount, 5) / (mean(kpl_float_market_cap, 5) + 1.0)",
            ("qd_limit_event",),
            ("kpl_float_market_cap", "kpl_main_net_amount"),
            5,
        ),
    )
    result: list[tuple[str, FactorSchema]] = []
    for domain, base, event, formula, sources, fields, horizon in templates:
        for direction, suffix in ((1, "positive"), (-1, "negative")):
            schema = FactorSchema(
                schema_id=f"{base}_{suffix}_{horizon}d",
                version="5.4.0",
                name=f"{base.replace('_', ' ')} {suffix}",
                event=event,
                context="market_wide_size_balanced_cross_section",
                quality="point_in_time_daily_and_event_inputs",
                direction=direction,
                output="cross_sectional_score",
                horizon=f"{horizon}d",  # type: ignore[arg-type]
                formula=formula,
                data_sources=sources,
                required_fields=tuple(sorted(fields)),
                availability_lag_days=0,
                economic_rationale=(
                    "Direction-complete constrained V5.4 hypothesis; economic mechanism is fixed before empirical evaluation."
                ),
            )
            schema.validate()
            result.append((domain, schema))
    if len(result) != 12 or len({schema.fingerprint for _, schema in result}) != 12:
        raise AssertionError("V5.4 requires exactly 12 fingerprint-unique hypotheses")
    return tuple(result)


def _usage_config(config: V54Config, scenario: str) -> V41Config:
    values = {
        "gross": (0.0, 0.0, 0.0, 0.0, 0.05),
        "standard": (3.0, 5.0, 5.0, 10.0, 0.05),
        "double": (6.0, 10.0, 10.0, 20.0, 0.05),
        "conservative": (3.0, 5.0, 15.0, 25.0, 0.02),
    }[scenario]
    return V41Config(
        primary_nav=config.nav,
        commission_bps=values[0],
        sell_tax_bps=values[1],
        slippage_bps=values[2],
        impact_bps=values[3],
        participation_rate=values[4],
        ingested_at=config.ingested_at,
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
            "2022-12-31",
            "2023-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
        )
    )


def _panel(
    schema: FactorSchema,
    bars: tuple[QmtDailyBar, ...],
    alternatives: dict[str, tuple],
    anchors: tuple,
    horizon: int,
) -> tuple[EvaluationObservation, ...]:
    required = {
        source: alternatives[source.removeprefix("qd_")]
        for source in schema.data_sources
        if source != "qd_daily"
    }
    built = build_multisource_factor_observations(bars, required, schema.compile(), anchors)
    return tuple(
        EvaluationObservation(
            timestamp=row.execution_at,
            instrument=row.instrument,
            factor_value=schema.direction * row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon=f"{horizon}d",
            subperiod=row.execution_at[:4],
            regime="unspecified",
        )
        for row in built
        if row.eligible
    )


def _annual_conversion(
    candidate_id: str,
    rows: tuple[EvaluationObservation, ...],
    *,
    year: int,
    horizon: int,
    breadth: int,
    config: V54Config,
    by_instrument: dict[str, dict[str, QmtDailyBar]],
    calendar: tuple[str, ...],
) -> AnnualConversion:
    metrics = _daily_metrics(rows)
    if not metrics:
        raise ValueError(f"empty V5.4 metrics: {candidate_id}:{year}:{horizon}")
    spec = UsageSpec("BUY", breadth, "all")
    gross, _ = evaluate_usage(
        candidate_id,
        rows,
        rows,
        spec,
        year=year,
        horizon=horizon,
        nav=config.nav,
        bars=by_instrument,
        calendar=calendar,
        regimes={},
        config=_usage_config(config, "gross"),
    )
    net, _ = evaluate_usage(
        candidate_id,
        rows,
        rows,
        spec,
        year=year,
        horizon=horizon,
        nav=config.nav,
        bars=by_instrument,
        calendar=calendar,
        regimes={},
        config=_usage_config(config, "standard"),
    )
    events, clipped = evaluate_usage_events(
        rows,
        rows,
        spec,
        horizon=horizon,
        nav=config.nav,
        bars=by_instrument,
        calendar=calendar,
        regimes={},
        config=_usage_config(config, "standard"),
    )
    controls, _ = evaluate_usage_events(
        rows,
        rows,
        UsageSpec("AVOID", 0, "all"),
        horizon=horizon,
        nav=config.nav,
        bars=by_instrument,
        calendar=calendar,
        regimes={},
        config=_usage_config(config, "standard"),
    )
    path = summarize_paths(
        year,
        events,
        controls,
        horizon=horizon,
        portfolio_sharpe=net.excess_sharpe,
        portfolio_return=net.cumulative_excess_return,
        portfolio_drawdown=net.maximum_drawdown,
    )
    grouped: dict[str, int] = defaultdict(int)
    for row in rows:
        grouped[row.timestamp[:10]] += 1
    shape = economic_shape(candidate_id, rows, year=year, regimes={})
    return AnnualConversion(
        year,
        len(metrics),
        len(rows),
        mean(item.rank_ic for item in metrics),
        mean(item.top_bottom for item in metrics),
        gross.cumulative_excess_return,
        net.cumulative_excess_return,
        net.excess_sharpe,
        gross.cumulative_excess_return - net.cumulative_excess_return,
        net.mean_turnover,
        net.total_cost_rate,
        net.active_days,
        path.positive_return_paths,
        path.paths,
        shape.monotonicity,
        min(grouped.values()),
        mean(grouped.values()),
        clipped,
    )


def _cost_tolerance(gross: float, net: float) -> float:
    drag = gross - net
    if gross <= 0:
        return 0.0
    if drag <= 0:
        return math.inf
    return gross / drag


def _stable_generated(
    years: tuple[AnnualConversion, ...], *, minimum_path_fraction: float
) -> bool:
    by_year = {item.year: item for item in years}
    return all(
        by_year[year].rank_ic > 0
        and by_year[year].net_excess_return > 0
        and by_year[year].positive_paths
        >= math.ceil(by_year[year].paths * minimum_path_fraction)
        for year in (2023, 2024)
    )


def _decay_from_quarters(quarters: tuple[float | None, ...]) -> bool:
    valid = [value for value in quarters if value is not None]
    return len(valid) >= 2 and valid[-1] < 0 and valid[-2] < 0


def run_v54_alpha_conversion(
    daily_dir: str | Path,
    screening_membership_path: str | Path,
    validation_membership_path: str | Path,
    *,
    auction_dir: str | Path,
    margin_dir: str | Path,
    limit_event_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V54Config | None = None,
    prior_inferential_trials: int = 1280,
) -> V54Report:
    config = config or V54Config()
    config.validate()
    if prior_inferential_trials < 1280:
        raise ValueError("V5.4 cannot discard the 1,280 pre-existing Trials")
    screening_memberships, screening_sha = _load_memberships(screening_membership_path, 10_000)
    validation_memberships, validation_sha = _load_memberships(validation_membership_path, 10_000)
    if set(screening_memberships) != set(validation_memberships):
        raise ValueError("V5.4 screening and validation membership dates differ")
    instruments = tuple(sorted({item for members in screening_memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date=config.data_end)
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=config.data_end,
        instruments=instruments,
    )
    alternatives: dict[str, tuple] = {}
    hashes: dict[str, str] = {}
    for kind, source in (
        ("auction", auction_dir),
        ("margin", margin_dir),
        ("limit_event", limit_event_dir),
    ):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.data_start,
                end_date=config.data_end,
                ingested_at=config.ingested_at,
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "screening_membership": screening_sha,
            "validation_membership": validation_sha,
            **hashes,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V54_VERSION,
        notes="Fixed conversion diagnostics and constrained generation; reused 2022-2024 evidence",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V5.4 Alpha conversion diagnostics",
            "Positive RankIC may fail economically because horizon, breadth and execution costs consume the edge.",
            snapshot_id,
            code_version,
            json.dumps({"version": V54_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    execution = _execution_memberships(screening_memberships, calendar)
    frozen = {schema.schema_id: (domain, schema) for domain, schema in independent_schemas()}
    if set(DIAGNOSTIC_IDS) - set(frozen):
        raise ValueError("V5.4 frozen diagnostic signal is not reproducible")

    cells: list[ConversionCell] = []
    for candidate_id in DIAGNOSTIC_IDS:
        domain, schema = frozen[candidate_id]
        for horizon in config.diagnostic_horizons:
            anchors = tuple(
                row
                for year in YEARS
                for row in _anchors(
                    year=year,
                    horizon=horizon,
                    calendar=calendar,
                    bars=by_instrument,
                    execution_members=execution,
                )
            )
            panel = _panel(schema, daily.bars, alternatives, anchors, horizon)
            for breadth in config.diagnostic_breadths:
                trial_id, trial_number = _trial(
                    registry,
                    experiment_id,
                    stage="v5.4_fixed_conversion_diagnostic",
                    factor_set=candidate_id,
                    parameters={"horizon": horizon, "breadth": breadth, "nav": config.nav},
                    seed=config.seed,
                )
                years = tuple(
                    _annual_conversion(
                        candidate_id,
                        tuple(row for row in panel if row.timestamp.startswith(f"{year}-")),
                        year=year,
                        horizon=horizon,
                        breadth=breadth,
                        config=config,
                        by_instrument=by_instrument,
                        calendar=calendar,
                    )
                    for year in YEARS
                )
                gross = math.prod(1 + item.gross_excess_return for item in years) - 1
                net = math.prod(1 + item.net_excess_return for item in years) - 1
                result = ConversionCell(
                    candidate_id,
                    domain,
                    horizon,
                    breadth,
                    years,
                    gross,
                    net,
                    gross - net,
                    _cost_tolerance(gross, net),
                    trial_id,
                    trial_number,
                )
                registry.record_trial_result(trial_id, json.dumps(asdict(result), sort_keys=True))
                cells.append(result)
            del panel
            gc.collect()
    if len(cells) != 36:
        raise AssertionError("V5.4 conversion grid must produce exactly 36 Trials")

    generated: list[GeneratedCandidate] = []
    for domain, schema in constrained_schemas():
        horizon = int(schema.horizon.removesuffix("d"))
        anchors = tuple(
            row
            for year in YEARS
            for row in _anchors(
                year=year,
                horizon=horizon,
                calendar=calendar,
                bars=by_instrument,
                execution_members=execution,
            )
        )
        panel = _panel(schema, daily.bars, alternatives, anchors, horizon)
        trial_id, trial_number = _trial(
            registry,
            experiment_id,
            stage="v5.4_constrained_generated_candidate",
            factor_set=schema.schema_id,
            parameters={
                "domain": domain,
                "fingerprint": schema.fingerprint,
                "horizon": horizon,
                "breadth": config.generated_breadth,
            },
            seed=config.seed,
        )
        years = tuple(
            _annual_conversion(
                schema.schema_id,
                tuple(row for row in panel if row.timestamp.startswith(f"{year}-")),
                year=year,
                horizon=horizon,
                breadth=config.generated_breadth,
                config=config,
                by_instrument=by_instrument,
                calendar=calendar,
            )
            for year in YEARS
        )
        quarters = tuple(
            value
            for item in years
            for value in _quarterly(
                _daily_metrics(
                    tuple(row for row in panel if row.timestamp.startswith(f"{item.year}-"))
                )
            )
        )
        decay = _decay_from_quarters(quarters)
        stable = (
            _stable_generated(
                years, minimum_path_fraction=config.minimum_positive_path_fraction
            )
            and not decay
        )
        by_year = {item.year: item for item in years}
        objective = min(by_year[2023].rank_ic, by_year[2024].rank_ic) + 0.25 * mean(
            (by_year[2023].net_excess_return, by_year[2024].net_excess_return)
        )
        item = GeneratedCandidate(
            schema.schema_id,
            schema.fingerprint,
            domain,
            schema.direction,
            horizon,
            schema.formula,
            years,
            stable,
            decay,
            objective,
            trial_id,
            trial_number,
        )
        registry.record_trial_result(trial_id, json.dumps(asdict(item), sort_keys=True))
        generated.append(item)
        del panel
        gc.collect()
    if len(generated) != 12:
        raise AssertionError("V5.4 constrained generator must produce 12 Trials")

    selected = []
    for domain in ("margin", "auction", "limit_event"):
        pool = [item for item in generated if item.domain == domain and item.stable]
        if pool:
            selected.append(max(pool, key=lambda item: (item.objective, item.candidate_id)))

    stresses: list[GeneratedStress] = []
    if selected:
        validation_instruments = tuple(
            sorted({item for members in validation_memberships.values() for item in members})
        )
        validation_daily = load_qd_daily_directory(
            root,
            start_date=config.data_start,
            end_date=config.data_end,
            instruments=validation_instruments,
        )
        validation_alternatives: dict[str, tuple] = {}
        for kind, source in (
            ("auction", auction_dir),
            ("margin", margin_dir),
            ("limit_event", limit_event_dir),
        ):
            validation_alternatives[kind] = load_qd_alternative_directory(
                source,
                QdAlternativeConfig(
                    source_kind=kind,  # type: ignore[arg-type]
                    start_date=config.data_start,
                    end_date=config.data_end,
                    ingested_at=config.ingested_at,
                    instruments=validation_instruments,
                ),
            ).observations
        validation_calendar = tuple(
            sorted({item.trade_date for item in validation_daily.bars})
        )
        validation_by_instrument: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
        for bar in validation_daily.bars:
            validation_by_instrument[bar.instrument][bar.trade_date] = bar
        validation_execution = _execution_memberships(
            validation_memberships, validation_calendar
        )
        schema_map = {schema.schema_id: schema for _, schema in constrained_schemas()}
        for selected_item in selected:
            schema = schema_map[selected_item.candidate_id]
            horizon = selected_item.horizon
            panel = _panel(
                schema,
                validation_daily.bars,
                validation_alternatives,
                tuple(
                    row
                    for year in YEARS
                    for row in _anchors(
                        year=year,
                        horizon=horizon,
                        calendar=validation_calendar,
                        bars=validation_by_instrument,
                        execution_members=validation_execution,
                    )
                ),
                horizon,
            )
            for scenario in STRESS_SCENARIOS:
                trial_id, trial_number = _trial(
                    registry,
                    experiment_id,
                    stage="v5.4_generated_candidate_stress",
                    factor_set=selected_item.candidate_id,
                    parameters={"scenario": scenario, "horizon": horizon, "breadth": 50},
                    seed=config.seed,
                )
                annual_returns = []
                annual_paths = []
                clipped = 0.0
                for year in YEARS:
                    rows = tuple(row for row in panel if row.timestamp.startswith(f"{year}-"))
                    spec = UsageSpec("BUY", 50, "all")
                    score, _ = evaluate_usage(
                        selected_item.candidate_id,
                        rows,
                        rows,
                        spec,
                        year=year,
                        horizon=horizon,
                        nav=config.nav,
                        bars=validation_by_instrument,
                        calendar=validation_calendar,
                        regimes={},
                        config=_usage_config(config, scenario),
                    )
                    events, clipped_year = evaluate_usage_events(
                        rows,
                        rows,
                        spec,
                        horizon=horizon,
                        nav=config.nav,
                        bars=validation_by_instrument,
                        calendar=validation_calendar,
                        regimes={},
                        config=_usage_config(config, scenario),
                    )
                    controls, _ = evaluate_usage_events(
                        rows,
                        rows,
                        UsageSpec("AVOID", 0, "all"),
                        horizon=horizon,
                        nav=config.nav,
                        bars=validation_by_instrument,
                        calendar=validation_calendar,
                        regimes={},
                        config=_usage_config(config, scenario),
                    )
                    path = summarize_paths(
                        year,
                        events,
                        controls,
                        horizon=horizon,
                        portfolio_sharpe=score.excess_sharpe,
                        portfolio_return=score.cumulative_excess_return,
                        portfolio_drawdown=score.maximum_drawdown,
                    )
                    annual_returns.append(score.cumulative_excess_return)
                    annual_paths.append(path.positive_return_paths)
                    clipped += clipped_year
                stress = GeneratedStress(
                    selected_item.candidate_id,
                    selected_item.domain,
                    scenario,
                    math.prod(1 + value for value in annual_returns) - 1,
                    min(annual_paths),
                    clipped,
                    trial_id,
                    trial_number,
                )
                registry.record_trial_result(trial_id, json.dumps(asdict(stress), sort_keys=True))
                stresses.append(stress)
            del panel
            gc.collect()

    failures = []
    if not selected:
        failures.append("no_stable_generated_candidate")
    if selected and any(
        stress.compounded_net_excess <= 0
        or stress.minimum_positive_paths
        < math.ceil(
            next(
                item.horizon
                for item in selected
                if item.candidate_id == stress.candidate_id
            )
            * config.minimum_positive_path_fraction
        )
        for stress in stresses
    ):
        failures.append("generated_candidate_stress")
    decision = "DEVELOPMENT_LEAD" if selected and not failures else "NO_CONVERTIBLE_ALPHA"
    best = max(
        cells,
        key=lambda item: (
            item.compounded_net_excess,
            item.cost_tolerance_multiplier,
            -item.horizon,
            -item.breadth,
            item.candidate_id,
        ),
    )
    diagnostic_conclusion = (
        "POSITIVE_CONVERSION_CELL"
        if best.compounded_net_excess > 0
        else "NO_POSITIVE_FIXED_FORMULA_CONVERSION"
    )
    report = V54Report(
        V54_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        len(cells),
        tuple(cells),
        best,
        diagnostic_conclusion,
        len(generated),
        tuple(generated),
        sum(item.stable for item in generated),
        tuple(selected),
        len(stresses),
        tuple(stresses),
        prior_inferential_trials,
        prior_inferential_trials + registry.global_trial_count(),
        decision,
        tuple(failures),
        "2022-2024 reused development evidence; no final or deployment claim",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.4-alpha-conversion.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v5.4-alpha-conversion.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v5.4-alpha-conversion.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
