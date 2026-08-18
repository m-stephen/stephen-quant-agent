from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean

from stephen_quant.cross_validation import SplitLineage
from stephen_quant.discovery import FactorSchema
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import deflated_sharpe_ratio, run_rank_placebo_fast
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
from .v4_ohlcv_platform import residualize_panel
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
from .v46_orthogonal_search import (
    CandidateEvidence,
    YearEvidence,
    _decay_alarm,
    _ensemble_panel,
    _quarterly,
    select_orthogonal,
)
from .v50_market_wide_search import (
    YEARS,
    _candidate_pbo,
    _execution_tiers,
    _incremental_returns,
    _load_tiers,
    _moments,
)
from .v51_candidate_audit import _style_controls

V53_VERSION = "v5.3-independent-mechanism-search-1.0.0"
DOMAINS = ("margin", "auction", "limit_event")
BASE_SCHEMA_IDS = (
    "margin_buy_intensity_20_20d",
    "margin_demand_acceleration_5_20_20_20d",
    "margin_crowding_reversal_20_20_20d",
    "auction_price_absorption_5_20_20d",
    "limit_up_persistence_20_20_20d",
    "limit_up_main_net_intensity_5_20_20d",
    "limit_up_seal_strength_5_20_20d",
)
SIGNAL_REPRESENTATIONS = ("raw", "style_residual")
EXECUTION_SCENARIOS = ("standard", "double", "conservative")


@dataclass(frozen=True)
class V53Config:
    data_start: str = "2021-01-01"
    data_end: str = "2024-12-31"
    years: tuple[int, ...] = YEARS
    horizon: int = 20
    breadth: int = 50
    nav: float = 3_000_000.0
    maximum_orthogonal_correlation: float = 0.75
    minimum_ensemble_domains: int = 2
    minimum_positive_paths: int = 15
    minimum_dsr: float = 0.95
    maximum_pbo: float = 0.05
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    cpcv_groups: int = 6
    cpcv_test_groups: int = 3
    embargo_days: int = 5
    ingested_at: str = "2026-08-19T00:00:00+08:00"
    seed: int = 43

    def validate(self) -> None:
        if (self.data_start, self.data_end) != ("2021-01-01", "2024-12-31"):
            raise ValueError("V5.3 data window is frozen")
        if self.years != YEARS or (self.horizon, self.breadth) != (20, 50):
            raise ValueError("V5.3 years, horizon and breadth are frozen")
        if self.nav != 3_000_000.0 or self.minimum_positive_paths != 15:
            raise ValueError("V5.3 NAV and path gate are frozen")
        if (self.cpcv_groups, self.cpcv_test_groups, self.embargo_days) != (6, 3, 5):
            raise ValueError("V5.3 CPCV design is frozen")
        if (self.minimum_dsr, self.maximum_pbo, self.maximum_placebo_p) != (
            0.95,
            0.05,
            0.05,
        ):
            raise ValueError("V5.3 falsification gates are frozen")


@dataclass(frozen=True)
class MechanismStress:
    signal_representation: str
    execution_scenario: str
    annual_rank_ic: tuple[tuple[int, float], ...]
    path: PathRobustness
    capacity_clipped_notional: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V53Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    candidate_trials: int
    validation_trials: int
    candidates: tuple[CandidateEvidence, ...]
    stable_candidates: int
    selected_candidates: tuple[CandidateEvidence, ...]
    pairwise_ic_correlations: tuple[tuple[str, str, float], ...]
    stresses: tuple[MechanismStress, ...]
    pbo_probability: float
    signal_placebo_p: float | None
    return_placebo_p: float | None
    dsr_probability: float | None
    dsr_skewness: float | None
    dsr_excess_kurtosis: float | None
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
        lines = [
            "# V5.3 独立机制 Alpha 搜索" if zh else "# V5.3 Independent-mechanism Alpha Search",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选 Trials' if zh else 'Candidate Trials'}: {self.candidate_trials}",
            f"- {'验证 Trials' if zh else 'Validation Trials'}: {self.validation_trials}",
            f"- {'累计 Trials' if zh else 'Cumulative Trials'}: {self.recorded_trial_count}",
            f"- PBO: {self.pbo_probability:.6f}",
            f"- DSR: {self.dsr_probability if self.dsr_probability is not None else 'N/A'}",
            f"- Placebo: {self.signal_placebo_p} / {self.return_placebo_p}",
            "",
            "## 入选机制" if zh else "## Selected mechanisms",
            "",
            "| Candidate | Domain | 2022 IC | 2023 IC | 2024 IC | Objective |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for item in self.selected_candidates:
            yearly = {row.year: row.mean_rank_ic for row in item.years}
            lines.append(
                f"| `{item.candidate_id}` | {item.domain} | {yearly[2022]:.4f} | "
                f"{yearly[2023]:.4f} | {yearly[2024]:.4f} | {item.objective:.4f} |"
            )
        lines.extend(
            [
                "",
                "## 固定验证网格" if zh else "## Frozen validation grid",
                "",
                "| Signal | Execution | Excess | Positive paths | Q25 Sharpe | Clipped |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for item in self.stresses:
            lines.append(
                f"| {item.signal_representation} | {item.execution_scenario} | "
                f"{item.path.portfolio_excess_return:.2%} | "
                f"{item.path.positive_return_paths}/{item.path.paths} | "
                f"{item.path.lower_quartile_sharpe:.3f} | "
                f"{item.capacity_clipped_notional:.2f} |"
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


def independent_schemas() -> tuple[tuple[str, FactorSchema], ...]:
    available: dict[str, FactorSchema] = {}
    for schema in all_schemas(generation_plans()):
        available.setdefault(schema.schema_id, schema)
    result = []
    for schema_id in BASE_SCHEMA_IDS:
        schema = available.get(schema_id)
        if schema is None:
            raise ValueError(f"missing frozen V5.3 schema: {schema_id}")
        domain = information_domain(schema)
        if domain not in DOMAINS:
            raise ValueError(f"V5.3 schema has forbidden domain: {schema_id}:{domain}")
        for direction, suffix in ((1, "positive"), (-1, "negative")):
            result.append(
                (
                    domain,
                    replace(
                        schema,
                        schema_id=f"{schema.schema_id}_{suffix}",
                        name=f"{schema.name} ({suffix} direction)",
                        direction=direction,
                        economic_rationale=(
                            f"Direction-complete V5.3 test: {schema.economic_rationale}"
                        ),
                    ),
                )
            )
    if len(result) != 14 or len({schema.fingerprint for _, schema in result}) != 14:
        raise AssertionError("V5.3 requires 14 fingerprint-unique hypotheses")
    return tuple(result)


def _stable(years: tuple[YearEvidence, ...]) -> bool:
    if tuple(item.year for item in years) != YEARS:
        raise ValueError("V5.3 stability evidence must cover 2022-2024")
    return (
        years[1].mean_rank_ic > 0
        and years[2].mean_rank_ic > 0
        and min(item.mean_rank_ic for item in years) >= -0.02
        and sum(item.path.incremental_return > 0 for item in years) >= 2
        and sum(item.path.median_sharpe > 0 for item in years) >= 2
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
            "2020-01-01",
            "2022-12-31",
            "2023-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
        )
    )


def _usage_config(scenario: str, config: V53Config) -> V41Config:
    values = {
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


def _evaluate_stress(
    rows: tuple[EvaluationObservation, ...],
    *,
    representation: str,
    scenario: str,
    config: V53Config,
    by_instrument: dict[str, dict[str, object]],
    calendar: tuple[str, ...],
    registry: ExperimentRegistry,
    experiment_id: str,
    factor_set: str,
) -> tuple[MechanismStress, tuple[float, ...]]:
    usage_config = _usage_config(scenario, config)
    annual_ic = tuple(
        (
            year,
            mean(
                item.rank_ic
                for item in _daily_metrics(
                    tuple(row for row in rows if row.timestamp.startswith(f"{year}-"))
                )
            ),
        )
        for year in YEARS
    )
    events_all, controls_all = [], []
    returns, drawdowns, sharpes = [], [], []
    clipped = 0.0
    for year in YEARS:
        yearly = tuple(row for row in rows if row.timestamp.startswith(f"{year}-"))
        spec = UsageSpec("BUY", config.breadth, "all")
        events, clipped_year = evaluate_usage_events(
            yearly,
            yearly,
            spec,
            horizon=config.horizon,
            nav=config.nav,
            bars=by_instrument,
            calendar=calendar,
            regimes={},
            config=usage_config,
        )
        controls, _ = evaluate_usage_events(
            yearly,
            yearly,
            UsageSpec("AVOID", 0, "all"),
            horizon=config.horizon,
            nav=config.nav,
            bars=by_instrument,
            calendar=calendar,
            regimes={},
            config=usage_config,
        )
        score, _ = evaluate_usage(
            f"v53_{representation}_{scenario}",
            yearly,
            yearly,
            spec,
            year=year,
            horizon=config.horizon,
            nav=config.nav,
            bars=by_instrument,
            calendar=calendar,
            regimes={},
            config=usage_config,
        )
        events_all.extend(events)
        controls_all.extend(controls)
        clipped += clipped_year
        returns.append(score.cumulative_excess_return)
        drawdowns.append(score.maximum_drawdown)
        sharpes.append(score.excess_sharpe)
    path = summarize_paths(
        YEARS[0],
        tuple(events_all),
        tuple(controls_all),
        horizon=config.horizon,
        portfolio_sharpe=mean(sharpes),
        portfolio_return=math.prod(1 + value for value in returns) - 1,
        portfolio_drawdown=min(drawdowns),
    )
    trial_id, trial_number = _trial(
        registry,
        experiment_id,
        stage="v5.3_fixed_validation_grid",
        factor_set=factor_set,
        parameters={"representation": representation, "scenario": scenario},
        seed=config.seed,
    )
    result = MechanismStress(
        representation,
        scenario,
        annual_ic,
        path,
        clipped,
        trial_id,
        trial_number,
    )
    registry.record_trial_result(trial_id, json.dumps(asdict(result), sort_keys=True))
    return result, _incremental_returns(events_all, controls_all)


def run_v53_independent_search(
    daily_dir: str | Path,
    screening_membership_path: str | Path,
    validation_membership_path: str | Path,
    tiers_path: str | Path,
    *,
    auction_dir: str | Path,
    margin_dir: str | Path,
    limit_event_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V53Config | None = None,
    prior_inferential_trials: int = 1218,
) -> V53Report:
    config = config or V53Config()
    config.validate()
    if prior_inferential_trials < 1218:
        raise ValueError("V5.3 cannot discard the 1,218 pre-existing Trials")
    schemas = independent_schemas()
    screening_memberships, screening_sha = _load_memberships(screening_membership_path, 10_000)
    memberships, membership_sha = _load_memberships(validation_membership_path, 10_000)
    tiers, tiers_sha = _load_tiers(tiers_path)
    if set(screening_memberships) != set(memberships) or set(memberships) != set(tiers):
        raise ValueError("V5.3 membership and tier dates differ")
    screening_instruments = tuple(
        sorted({item for members in screening_memberships.values() for item in members})
    )
    validation_instruments = tuple(
        sorted({item for members in memberships.values() for item in members})
    )
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date=config.data_end)
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=config.data_end,
        instruments=screening_instruments,
    )
    alternatives = {}
    alternative_hashes = {}
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
                instruments=screening_instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        alternative_hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "market_wide_screening_membership": screening_sha,
            "market_wide_membership": membership_sha,
            "market_wide_tiers": tiers_sha,
            **alternative_hashes,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V53_VERSION,
        notes="Independent mechanism search; 2022-2024 reused development evidence",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V5.3 independent-mechanism search",
            "Margin, auction absorption and limit-event mechanisms may add style-robust information.",
            snapshot_id,
            code_version,
            json.dumps({"version": V53_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument: dict[str, dict[str, object]] = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    screening_execution = _execution_memberships(screening_memberships, calendar)
    anchors = tuple(
        row
        for year in YEARS
        for row in _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=by_instrument,
            execution_members=screening_execution,
        )
    )
    evidence: list[CandidateEvidence] = []
    daily_ics: dict[str, dict[str, float]] = {}
    intervals: dict[str, tuple[str, str, str]] = {}
    raw_candidate_sharpes: list[float] = []
    trial_ids: list[str] = []
    schema_by_id = {schema.schema_id: schema for _, schema in schemas}
    for domain, schema in schemas:
        required = {
            source: alternatives[source.removeprefix("qd_")]
            for source in schema.data_sources
            if source != "qd_daily"
        }
        trial_id, trial_number = _trial(
            registry,
            experiment_id,
            stage="v5.3_independent_candidate",
            factor_set=schema.schema_id,
            parameters={"domain": domain, "fingerprint": schema.fingerprint},
            seed=config.seed,
        )
        trial_ids.append(trial_id)
        built = build_multisource_factor_observations(
            daily.bars, required, schema.compile(), anchors
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
        yearly = []
        ic_series = {}
        for year in YEARS:
            rows = tuple(row for row in all_rows if row.timestamp.startswith(f"{year}-"))
            metrics = _daily_metrics(rows)
            if not metrics:
                raise ValueError(f"empty V5.3 metrics: {schema.schema_id}:{year}")
            ic_series.update({item.day: item.rank_ic for item in metrics})
            events, _ = evaluate_usage_events(
                rows,
                rows,
                UsageSpec("BUY", config.breadth, "all"),
                horizon=config.horizon,
                nav=config.nav,
                bars=by_instrument,
                calendar=calendar,
                regimes={},
                config=_usage_config("standard", config),
            )
            controls, _ = evaluate_usage_events(
                rows,
                rows,
                UsageSpec("AVOID", 0, "all"),
                horizon=config.horizon,
                nav=config.nav,
                bars=by_instrument,
                calendar=calendar,
                regimes={},
                config=_usage_config("standard", config),
            )
            score, _ = evaluate_usage(
                schema.schema_id,
                rows,
                rows,
                UsageSpec("BUY", config.breadth, "all"),
                year=year,
                horizon=config.horizon,
                nav=config.nav,
                bars=by_instrument,
                calendar=calendar,
                regimes={},
                config=_usage_config("standard", config),
            )
            path = summarize_paths(
                year,
                events,
                controls,
                horizon=config.horizon,
                portfolio_sharpe=score.excess_sharpe,
                portfolio_return=score.cumulative_excess_return,
                portfolio_drawdown=score.maximum_drawdown,
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
        for row in all_rows:
            day = row.timestamp[:10]
            current = intervals.get(day)
            candidate = (row.factor_available_at, row.label_start_at, row.label_end_at)
            if current is None:
                intervals[day] = candidate
            elif current[1:] == candidate[1:]:
                intervals[day] = (max(current[0], candidate[0]), current[1], current[2])
            else:
                raise ValueError("V5.3 candidate label intervals differ")
        years = tuple(yearly)
        result = CandidateEvidence(
            schema.schema_id,
            schema.fingerprint,
            domain,
            schema.direction,
            years,
            _stable(years),
            _decay_alarm(years),
            min(item.mean_rank_ic for item in years[1:])
            + mean(item.mean_rank_ic for item in years),
            trial_id,
            trial_number,
        )
        registry.record_trial_result(trial_id, json.dumps(asdict(result), sort_keys=True))
        evidence.append(result)
        daily_ics[schema.schema_id] = ic_series
        raw_candidate_sharpes.append(
            mean(item.path.incremental_daily_sharpe for item in years) / math.sqrt(252)
        )
    selected, correlations = select_orthogonal(
        tuple(evidence),
        daily_ics,
        maximum_correlation=config.maximum_orthogonal_correlation,
    )
    pbo, _ = _candidate_pbo(
        daily_ics,
        intervals,
        registry_lineage=SplitLineage(snapshot_id, experiment_id, trial_ids[0], code_version),
        config=config,  # type: ignore[arg-type]
    )
    stresses: list[MechanismStress] = []
    signal_p = return_p = dsr = skewness = excess_kurtosis = None
    failures: list[str] = []
    if len(selected) < config.minimum_ensemble_domains:
        failures.append("insufficient_independent_domains")
    else:
        del daily, alternatives, by_instrument
        gc.collect()
        daily = load_qd_daily_directory(
            root,
            start_date=config.data_start,
            end_date=config.data_end,
            instruments=validation_instruments,
        )
        alternatives = {}
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
                    instruments=validation_instruments,
                ),
            )
            if dataset.audit.source_sha256 != alternative_hashes[kind]:
                raise ValueError(f"V5.3 {kind} source changed between stages")
            alternatives[kind] = dataset.observations
        calendar = tuple(sorted({item.trade_date for item in daily.bars}))
        by_instrument = defaultdict(dict)
        for bar in daily.bars:
            by_instrument[bar.instrument][bar.trade_date] = bar
        validation_execution = _execution_memberships(memberships, calendar)
        execution_tiers = _execution_tiers(tiers, calendar)
        validation_anchors = tuple(
            row
            for year in YEARS
            for row in _anchors(
                year=year,
                horizon=config.horizon,
                calendar=calendar,
                bars=by_instrument,
                execution_members=validation_execution,
            )
        )
        selected_panels = []
        for item in selected:
            schema = schema_by_id[item.candidate_id]
            required = {
                source: alternatives[source.removeprefix("qd_")]
                for source in schema.data_sources
                if source != "qd_daily"
            }
            built = build_multisource_factor_observations(
                daily.bars, required, schema.compile(), validation_anchors
            )
            selected_panels.append(
                tuple(
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
            )
        raw = tuple(
            row
            for year in YEARS
            for row in _ensemble_panel(
                tuple(
                    tuple(item for item in panel if item.timestamp.startswith(f"{year}-"))
                    for panel in selected_panels
                ),
                year=year,
            )
        )
        style = residualize_panel(
            raw,
            _style_controls(
                raw,
                by_instrument=by_instrument,
                calendar=calendar,
                execution_tiers=execution_tiers,
            ),
        )
        factor_set = "+".join(item.candidate_id for item in selected)
        incremental: dict[tuple[str, str], tuple[float, ...]] = {}
        for representation, rows in (("raw", raw), ("style_residual", style)):
            for scenario in EXECUTION_SCENARIOS:
                result, values = _evaluate_stress(
                    rows,
                    representation=representation,
                    scenario=scenario,
                    config=config,
                    by_instrument=by_instrument,
                    calendar=calendar,
                    registry=registry,
                    experiment_id=experiment_id,
                    factor_set=factor_set,
                )
                stresses.append(result)
                incremental[(representation, scenario)] = values
        raw_standard = next(
            item
            for item in stresses
            if (item.signal_representation, item.execution_scenario) == ("raw", "standard")
        )
        values = incremental[("raw", "standard")]
        skewness, excess_kurtosis = _moments(values)
        recorded = prior_inferential_trials + registry.global_trial_count()
        dsr = deflated_sharpe_ratio(
            observed_sharpe=raw_standard.path.incremental_daily_sharpe / math.sqrt(252),
            trial_sharpes=raw_candidate_sharpes
            + [item.path.incremental_daily_sharpe / math.sqrt(252) for item in stresses],
            recorded_trial_count=recorded,
            observations=len(_daily_metrics(raw)),
            skewness=skewness,
            excess_kurtosis=excess_kurtosis,
        ).probability
        signal_p = run_rank_placebo_fast(
            raw,
            horizon="20d",
            direction=1,
            method="signal_shuffle",
            seed=config.seed,
            repetitions=config.placebo_repetitions,
            min_cross_section=10,
        ).empirical_p_value
        return_p = run_rank_placebo_fast(
            raw,
            horizon="20d",
            direction=1,
            method="return_permutation",
            seed=config.seed,
            repetitions=config.placebo_repetitions,
            min_cross_section=10,
        ).empirical_p_value
        for representation in SIGNAL_REPRESENTATIONS:
            standard = next(
                item
                for item in stresses
                if (item.signal_representation, item.execution_scenario)
                == (representation, "standard")
            )
            conservative = next(
                item
                for item in stresses
                if (item.signal_representation, item.execution_scenario)
                == (representation, "conservative")
            )
            if standard.path.portfolio_excess_return <= 0:
                failures.append(f"{representation}_standard_return")
            if conservative.path.portfolio_excess_return <= 0:
                failures.append(f"{representation}_conservative_return")
            if conservative.path.positive_return_paths < config.minimum_positive_paths:
                failures.append(f"{representation}_conservative_paths")
        if any(item.capacity_clipped_notional > 0 for item in stresses):
            failures.append("capacity_clipping")
        if signal_p > config.maximum_placebo_p:
            failures.append("signal_placebo")
        if return_p > config.maximum_placebo_p:
            failures.append("return_placebo")
        if dsr < config.minimum_dsr:
            failures.append("multiplicity_dsr")
    if pbo > config.maximum_pbo:
        failures.append("candidate_selection_pbo")
    report = V53Report(
        V53_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        len(evidence),
        len(stresses),
        tuple(evidence),
        sum(item.stable and not item.decay_alarm for item in evidence),
        selected,
        correlations,
        tuple(stresses),
        pbo,
        signal_p,
        return_p,
        dsr,
        skewness,
        excess_kurtosis,
        prior_inferential_trials + registry.global_trial_count(),
        "DEVELOPMENT_LEAD" if not failures else "NO_INDEPENDENT_ALPHA",
        tuple(dict.fromkeys(failures)),
        "2022-2024 reused development evidence; requires genuinely new forward data",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.3-independent-search.json").write_text(report.to_json() + "\n", encoding="utf-8")
    for language in ("zh", "en"):
        (output / f"v5.3-independent-search.{language}.md").write_text(
            report.to_markdown(language) + "\n", encoding="utf-8"
        )
    return report
