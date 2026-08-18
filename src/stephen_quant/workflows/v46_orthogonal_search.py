from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean

from stephen_quant.discovery import FactorSchema
from stephen_quant.evaluation import EvaluationObservation, pearson_correlation
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeConfig,
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
    evaluate_usage,
    evaluate_usage_events,
)
from .v43_domain_breadth import _schemas as all_schemas
from .v43_domain_breadth import generation_plans, information_domain
from .v44_path_robust_alpha import PathRobustness, summarize_paths

V46_VERSION = "v4.6-bounded-orthogonal-search-1.0.0"
DOMAINS = ("auction", "fund_flow", "chip")
YEARS = (2022, 2023, 2024, 2025)
BASE_PREFIXES = {
    "auction": (
        "auction_strength_5_20d",
        "auction_strength_20_20d",
        "auction_amount_intensity_5_20d",
        "auction_amount_intensity_20_20d",
        "auction_liquidity_strength_5_20d",
        "auction_liquidity_strength_20_20d",
    ),
    "fund_flow": (
        "fund_flow_intensity_5_20d",
        "fund_flow_intensity_20_20d",
        "extra_large_flow_intensity_5_20d",
        "extra_large_flow_intensity_20_20d",
        "flow_price_divergence_5_20d",
        "flow_price_divergence_20_20d",
    ),
    "chip": (
        "chip_concentrated_momentum_5_20_20d",
        "chip_cost_gap_reversal_5_20_20d",
        "chip_profit_crowding_reversal_5_20_20d",
        "chip_cost_band_compression_5_20_20_20d",
        "chip_cost_basis_momentum_confirmation_5_20_20d",
        "chip_win_rate_acceleration_5_20_20_20d",
    ),
}


@dataclass(frozen=True)
class V46Config:
    data_start: str = "2021-01-01"
    years: tuple[int, ...] = YEARS
    universe_top_n: int = 50
    horizon: int = 20
    breadth: int = 10
    domain_budget: int = 12
    primary_nav: float = 3_000_000.0
    stress_nav: float = 20_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_positive_ic_years: int = 3
    minimum_positive_return_years: int = 3
    minimum_year_rank_ic: float = -0.02
    minimum_validation_rank_ic: float = 0.0
    maximum_orthogonal_correlation: float = 0.75
    minimum_ensemble_domains: int = 2
    minimum_development_sharpe: float = 0.50
    minimum_positive_stress_fraction: float = 0.75
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if self.years != YEARS or self.horizon != 20 or self.breadth != 10:
            raise ValueError("V4.6 years, horizon and breadth are frozen")
        if self.domain_budget != 12:
            raise ValueError("V4.6 domain budget is frozen at 12")
        if self.primary_nav != 3_000_000.0 or self.stress_nav != 20_000_000.0:
            raise ValueError("V4.6 NAV grid is frozen")


@dataclass(frozen=True)
class YearEvidence:
    year: int
    dates: int
    mean_rank_ic: float
    mean_top_bottom: float
    quarterly_rank_ic: tuple[float | None, ...]
    path: PathRobustness


@dataclass(frozen=True)
class CandidateEvidence:
    candidate_id: str
    fingerprint: str
    domain: str
    direction: int
    years: tuple[YearEvidence, ...]
    stable: bool
    decay_alarm: bool
    objective: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class EnsembleStress:
    nav: float
    cost_multiplier: float
    path: PathRobustness
    capacity_clipped_notional: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V46Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    candidate_trials: int
    candidates_per_domain: tuple[tuple[str, int], ...]
    stable_candidates: int
    selected_candidates: tuple[CandidateEvidence, ...]
    pairwise_ic_correlations: tuple[tuple[str, str, float], ...]
    ensemble_stress: tuple[EnsembleStress, ...]
    positive_stress_fraction: float
    signal_placebo_p: float | None
    return_placebo_p: float | None
    dsr_probability: float | None
    recorded_trial_count: int
    decision: str
    failures: tuple[str, ...]
    evidence_status: str
    forward_shadow_start: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.6 三域正交 Alpha 研究" if zh else "# V4.6 Three-Domain Orthogonal Alpha Research",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选 Trials' if zh else 'Candidate trials'}: {self.candidate_trials}",
            f"- {'稳定候选' if zh else 'Stable candidates'}: {self.stable_candidates}",
            f"- {'正收益压力比例' if zh else 'Positive stress fraction'}: {self.positive_stress_fraction:.2%}",
            f"- DSR: {self.dsr_probability if self.dsr_probability is not None else 'N/A'}",
            f"- {'证据级别' if zh else 'Evidence status'}: {self.evidence_status}",
            "",
            "| Candidate | Domain | Objective | Decay | 2022 IC | 2023 IC | 2024 IC | 2025 IC |",
            "|---|---|---:|---|---:|---:|---:|---:|",
        ]
        for item in self.selected_candidates:
            values = {year.year: year.mean_rank_ic for year in item.years}
            lines.append(
                f"| `{item.candidate_id}` | {item.domain} | {item.objective:.4f} | "
                f"{item.decay_alarm} | {values[2022]:.4f} | {values[2023]:.4f} | "
                f"{values[2024]:.4f} | {values[2025]:.4f} |"
            )
        lines.extend(
            [
                "",
                (
                    f"- {'失败门禁' if zh else 'Failed gates'}: "
                    f"{', '.join(self.failures) or ('无' if zh else 'none')}"
                ),
                f"- {'前向 Shadow 起始' if zh else 'Forward shadow start'}: {self.forward_shadow_start}",
                "",
            ]
        )
        return "\n".join(lines)


def curated_schemas() -> tuple[tuple[str, FactorSchema], ...]:
    available = {schema.schema_id: schema for schema in all_schemas(generation_plans())}
    result: list[tuple[str, FactorSchema]] = []
    for domain in DOMAINS:
        bases = []
        for schema_id in BASE_PREFIXES[domain]:
            schema = available.get(schema_id)
            if schema is None or information_domain(schema) != domain:
                raise ValueError(f"missing frozen V4.6 schema: {schema_id}")
            bases.append(schema)
        for schema in bases:
            result.append((domain, schema))
            result.append(
                (
                    domain,
                    replace(
                        schema,
                        schema_id=f"{schema.schema_id}_inverse",
                        name=f"{schema.name} inverse",
                        direction=-schema.direction,
                        economic_rationale=f"Direction-complete falsification: {schema.economic_rationale}",
                    ),
                )
            )
    if len(result) != 36:
        raise AssertionError("V4.6 must contain exactly 36 hypotheses")
    for domain in DOMAINS:
        if sum(item[0] == domain for item in result) != 12:
            raise AssertionError(f"V4.6 domain budget drift: {domain}")
    if len({schema.fingerprint for _, schema in result}) != len(result):
        raise AssertionError("V4.6 hypotheses must be fingerprint-unique")
    return tuple(result)


def stable_candidate(years: tuple[YearEvidence, ...], config: V46Config) -> bool:
    if tuple(item.year for item in years) != YEARS:
        raise ValueError("V4.6 evidence must cover 2022-2025")
    positive_ic = sum(item.mean_rank_ic > 0 for item in years)
    positive_return = sum(item.path.incremental_return > 0 for item in years)
    validation = years[1:]
    return (
        positive_ic >= config.minimum_positive_ic_years
        and positive_return >= config.minimum_positive_return_years
        and min(item.mean_rank_ic for item in years) >= config.minimum_year_rank_ic
        and all(item.mean_rank_ic > config.minimum_validation_rank_ic for item in validation)
        and sum(item.path.median_sharpe > 0 for item in years) >= 3
    )


def _decay_alarm(years: tuple[YearEvidence, ...]) -> bool:
    quarters = [value for item in years for value in item.quarterly_rank_ic]
    valid = [value for value in quarters if value is not None]
    return len(valid) >= 2 and valid[-1] < 0 and valid[-2] < 0


def select_orthogonal(
    candidates: tuple[CandidateEvidence, ...],
    daily_ics: dict[str, dict[str, float]],
    *,
    maximum_correlation: float,
) -> tuple[tuple[CandidateEvidence, ...], tuple[tuple[str, str, float], ...]]:
    pool = sorted(
        (item for item in candidates if item.stable and not item.decay_alarm),
        key=lambda item: (-item.objective, item.domain, item.candidate_id),
    )
    selected: list[CandidateEvidence] = []
    correlations: list[tuple[str, str, float]] = []
    used_domains: set[str] = set()
    for item in pool:
        if item.domain in used_domains:
            continue
        acceptable = True
        pending: list[tuple[str, str, float]] = []
        for prior in selected:
            common = sorted(set(daily_ics[item.candidate_id]) & set(daily_ics[prior.candidate_id]))
            if len(common) < 3:
                acceptable = False
                continue
            correlation = pearson_correlation(
                [daily_ics[item.candidate_id][day] for day in common],
                [daily_ics[prior.candidate_id][day] for day in common],
            )
            pending.append((prior.candidate_id, item.candidate_id, correlation))
            if abs(correlation) > maximum_correlation:
                acceptable = False
        if acceptable:
            correlations.extend(pending)
            selected.append(item)
            used_domains.add(item.domain)
    return tuple(selected), tuple(correlations)


def _ensemble_panel(
    panels: tuple[tuple[EvaluationObservation, ...], ...], *, year: int
) -> tuple[EvaluationObservation, ...]:
    ranked: list[dict[tuple[str, str], tuple[float, EvaluationObservation]]] = []
    for panel in panels:
        grouped = defaultdict(list)
        for row in panel:
            grouped[row.timestamp[:10]].append(row)
        values = {}
        for day, cross in grouped.items():
            ordered = sorted(cross, key=lambda item: (item.factor_value, item.instrument))
            denominator = max(len(ordered) - 1, 1)
            for index, row in enumerate(ordered):
                values[(day, row.instrument)] = (index / denominator, row)
        ranked.append(values)
    common = set.intersection(*(set(item) for item in ranked)) if ranked else set()
    output = []
    for key in sorted(common):
        components = [item[key] for item in ranked]
        rows = [item[1] for item in components]
        if len({row.label_start_at for row in rows}) != 1 or len({row.label_end_at for row in rows}) != 1:
            raise ValueError("ensemble label grids differ")
        output.append(
            EvaluationObservation(
                timestamp=rows[0].timestamp,
                instrument=rows[0].instrument,
                factor_value=mean(item[0] for item in components),
                factor_available_at=max(row.factor_available_at for row in rows),
                label_start_at=rows[0].label_start_at,
                label_end_at=rows[0].label_end_at,
                forward_return=rows[0].forward_return,
                horizon="20d",
                subperiod=str(year),
                regime="unspecified",
            )
        )
    return tuple(output)


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
            "2024-12-31",
            "2025-01-01",
            "2025-12-31",
            "2026-08-19",
            "2027-08-18",
        )
    )


def _quarterly(metrics: tuple) -> tuple[float | None, ...]:
    grouped = defaultdict(list)
    for item in metrics:
        grouped[(int(item.day[5:7]) - 1) // 3 + 1].append(item.rank_ic)
    return tuple(mean(grouped[quarter]) if grouped[quarter] else None for quarter in range(1, 5))


def run_v46_orthogonal_search(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    chip_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V46Config | None = None,
    prior_inferential_trials: int = 1049,
) -> V46Report:
    config = config or V46Config()
    config.validate()
    schemas = curated_schemas()
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
    for kind, source in (("auction", auction_dir), ("fund_flow", fund_flow_dir), ("chip", chip_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date="2021-01-01",
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
        vendor_version=V46_VERSION,
        notes="2022-2025 development evidence only; no independent final window",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.6 bounded orthogonal search",
            "Orthogonal auction, fund-flow and chip mechanisms may provide more durable incremental selection information.",
            snapshot_id,
            code_version,
            json.dumps({"version": V46_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument = defaultdict(dict)
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
    anchors = {
        year: _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=by_instrument,
            execution_members=execution_members,
        )
        for year in YEARS
    }
    combined_anchors = tuple(row for year in YEARS for row in anchors[year])
    panels = {}
    evidence = []
    daily_ics = {}
    raw_candidate_sharpes = []
    for domain, schema in schemas:
        required = {
            source: alternatives[source.removeprefix("qd_")]
            for source in schema.data_sources
            if source != "qd_daily"
        }
        yearly = []
        ic_series = {}
        trial = _trial(
            registry,
            experiment_id,
            stage="v4.6_nested_candidate_development",
            factor_set=schema.schema_id,
            parameters={"domain": domain, "fingerprint": schema.fingerprint},
            seed=config.seed,
        )
        built = build_multisource_factor_observations(
            daily.bars,
            required,
            schema.compile(),
            combined_anchors,
        )
        all_rows = tuple(
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
        for year in YEARS:
            rows = tuple(
                row for row in all_rows if row.timestamp.startswith(f"{year}-")
            )
            panels[(schema.schema_id, year)] = rows
            metrics = _daily_metrics(rows)
            if not metrics:
                raise ValueError(f"empty V4.6 metrics: {schema.schema_id}:{year}")
            ic_series.update({item.day: item.rank_ic for item in metrics})
            spec = UsageSpec("AVOID", config.breadth, "all")
            candidate_events, _ = evaluate_usage_events(
                rows, rows, spec, horizon=config.horizon, nav=config.primary_nav,
                bars=by_instrument, calendar=calendar, regimes={}, config=usage_config,
            )
            controls, _ = evaluate_usage_events(
                rows, rows, UsageSpec("AVOID", 0, "all"), horizon=config.horizon,
                nav=config.primary_nav, bars=by_instrument, calendar=calendar, regimes={},
                config=usage_config,
            )
            portfolio, _ = evaluate_usage(
                schema.schema_id, rows, rows, spec, year=year, horizon=config.horizon,
                nav=config.primary_nav, bars=by_instrument, calendar=calendar, regimes={},
                config=usage_config,
            )
            path = summarize_paths(
                year, candidate_events, controls, horizon=config.horizon,
                portfolio_sharpe=portfolio.excess_sharpe,
                portfolio_return=portfolio.cumulative_excess_return,
                portfolio_drawdown=portfolio.maximum_drawdown,
            )
            yearly.append(
                YearEvidence(
                    year,
                    len(metrics),
                    mean(item.rank_ic for item in metrics),
                    mean(item.top_bottom for item in metrics),
                    _quarterly(metrics),
                    path,
                )
            )
        year_tuple = tuple(yearly)
        stable = stable_candidate(year_tuple, config)
        objective = min(item.mean_rank_ic for item in year_tuple[1:]) + mean(
            item.mean_rank_ic for item in year_tuple
        )
        candidate = CandidateEvidence(
            schema.schema_id,
            schema.fingerprint,
            domain,
            schema.direction,
            year_tuple,
            stable,
            _decay_alarm(year_tuple),
            objective,
            trial[0],
            trial[1],
        )
        registry.record_trial_result(trial[0], json.dumps(asdict(candidate), sort_keys=True))
        evidence.append(candidate)
        daily_ics[schema.schema_id] = ic_series
        raw_candidate_sharpes.append(
            mean(item.path.incremental_daily_sharpe for item in year_tuple) / math.sqrt(252)
        )
    selected, correlations = select_orthogonal(
        tuple(evidence), daily_ics, maximum_correlation=config.maximum_orthogonal_correlation
    )
    stress_results = []
    signal_p = return_p = dsr_probability = None
    failures = []
    if len(selected) < config.minimum_ensemble_domains:
        failures.append("insufficient_orthogonal_domains")
    else:
        ensemble_by_year = {
            year: _ensemble_panel(
                tuple(panels[(item.candidate_id, year)] for item in selected), year=year
            )
            for year in YEARS
        }
        stress_raw = []
        for nav in (config.primary_nav, config.stress_nav):
            for multiplier in (1.0, 2.0):
                stress_config = replace(
                    usage_config,
                    primary_nav=nav,
                    commission_bps=config.commission_bps * multiplier,
                    sell_tax_bps=config.sell_tax_bps * multiplier,
                    slippage_bps=config.slippage_bps * multiplier,
                    impact_bps=config.impact_bps * multiplier,
                )
                combined_events = []
                combined_controls = []
                combined_rows = []
                clipped = 0.0
                portfolio_returns = []
                portfolio_drawdowns = []
                portfolio_sharpes = []
                for year in YEARS:
                    rows = ensemble_by_year[year]
                    combined_rows.extend(rows)
                    spec = UsageSpec("AVOID", config.breadth, "all")
                    events, clipped_year = evaluate_usage_events(
                        rows, rows, spec, horizon=config.horizon, nav=nav, bars=by_instrument,
                        calendar=calendar, regimes={}, config=stress_config,
                    )
                    controls, _ = evaluate_usage_events(
                        rows, rows, UsageSpec("AVOID", 0, "all"), horizon=config.horizon,
                        nav=nav, bars=by_instrument, calendar=calendar, regimes={}, config=stress_config,
                    )
                    score, _ = evaluate_usage(
                        "v46_equal_weight_orthogonal_ensemble", rows, rows, spec, year=year,
                        horizon=config.horizon, nav=nav, bars=by_instrument, calendar=calendar,
                        regimes={}, config=stress_config,
                    )
                    combined_events.extend(events)
                    combined_controls.extend(controls)
                    clipped += clipped_year
                    portfolio_returns.append(score.cumulative_excess_return)
                    portfolio_drawdowns.append(score.maximum_drawdown)
                    portfolio_sharpes.append(score.excess_sharpe)
                trial = _trial(
                    registry,
                    experiment_id,
                    stage="v4.6_ensemble_stress",
                    factor_set="+".join(item.candidate_id for item in selected),
                    parameters={"nav": nav, "cost_multiplier": multiplier},
                    seed=config.seed,
                )
                path = summarize_paths(
                    2022,
                    tuple(combined_events),
                    tuple(combined_controls),
                    horizon=config.horizon,
                    portfolio_sharpe=mean(portfolio_sharpes),
                    portfolio_return=math.prod(1 + item for item in portfolio_returns) - 1,
                    portfolio_drawdown=min(portfolio_drawdowns),
                )
                result = EnsembleStress(nav, multiplier, path, clipped, trial[0], trial[1])
                registry.record_trial_result(trial[0], json.dumps(asdict(result), sort_keys=True))
                stress_results.append(result)
                stress_raw.append(path.incremental_daily_sharpe / math.sqrt(252))
        primary = next(
            item for item in stress_results
            if item.nav == config.primary_nav and item.cost_multiplier == 1.0
        )
        recorded_for_dsr = prior_inferential_trials + registry.global_trial_count()
        dsr_probability = deflated_sharpe_ratio(
            observed_sharpe=primary.path.incremental_daily_sharpe / math.sqrt(252),
            trial_sharpes=raw_candidate_sharpes + stress_raw,
            recorded_trial_count=recorded_for_dsr,
            observations=sum(item.dates for item in selected[0].years),
        ).probability
        placebo_rows = tuple(
            row for year in YEARS for row in ensemble_by_year[year]
        )
        signal_p = run_placebo(
            placebo_rows, horizon="20d", direction=1, method="signal_shuffle",
            seed=config.seed, repetitions=config.placebo_repetitions, min_cross_section=10,
        ).empirical_p_value
        return_p = run_placebo(
            placebo_rows, horizon="20d", direction=1, method="return_permutation",
            seed=config.seed, repetitions=config.placebo_repetitions, min_cross_section=10,
        ).empirical_p_value
        positive_fraction = sum(
            item.path.incremental_return > 0 and item.path.portfolio_excess_return > 0
            for item in stress_results
        ) / len(stress_results)
        if primary.path.incremental_daily_sharpe < config.minimum_development_sharpe:
            failures.append("ensemble_sharpe")
        if primary.path.incremental_return <= 0 or primary.path.portfolio_excess_return <= 0:
            failures.append("ensemble_return")
        if positive_fraction < config.minimum_positive_stress_fraction:
            failures.append("stress_robustness")
        if dsr_probability < config.minimum_dsr:
            failures.append("multiplicity_dsr")
        if signal_p > config.maximum_placebo_p:
            failures.append("signal_placebo")
        if return_p > config.maximum_placebo_p:
            failures.append("return_placebo")
    positive_fraction = (
        sum(
            item.path.incremental_return > 0 and item.path.portfolio_excess_return > 0
            for item in stress_results
        ) / len(stress_results)
        if stress_results
        else 0.0
    )
    report = V46Report(
        V46_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        len(evidence),
        tuple((domain, sum(item.domain == domain for item in evidence)) for domain in DOMAINS),
        sum(item.stable for item in evidence),
        selected,
        correlations,
        tuple(stress_results),
        positive_fraction,
        signal_p,
        return_p,
        dsr_probability,
        prior_inferential_trials + registry.global_trial_count(),
        "DEVELOPMENT_CANDIDATE" if not failures else "NO_DEVELOPMENT_ALPHA",
        tuple(failures),
        "2022-2025 reused development evidence; never independent final proof",
        "2026-08-19",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.6-orthogonal-search.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.6-orthogonal-search.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.6-orthogonal-search.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
